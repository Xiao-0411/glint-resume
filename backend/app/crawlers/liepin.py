"""
猎聘 爬虫 —— 目前唯一验证可用的真实职位数据源

接口要点（2026-08 实测）：
- 用 api-c.liepin.com 的 POST 接口，www.liepin.com/api/... 那条老路径已 404
- 必须带 X-Fscp-* 系列请求头，否则返回空
- city 必须是具体城市码，传 "0" 返回 0 条；"410" 是全国
- 列表接口不含 JD 正文，需再抓详情页
- PC 详情页 www.liepin.com/job/*.shtml 抓十几条后就被重定向到 wow.liepin.com
  营销页（配额型反爬，冷却也不恢复）。移动端 m.liepin.com 不受此限制，
  JD 正文在 .job-describe-duty 容器里，所以详情统一走移动端。
"""
import asyncio
import logging
import re
from typing import List, Optional

import httpx

from app.crawlers.base import BaseCrawler, JOB_KEYWORDS

logger = logging.getLogger("glint.crawler.liepin")

LIEPIN_SEARCH_URL = "https://api-c.liepin.com/api/com.liepin.searchfront4c.pc-search-job"

MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)
# 命中此域名说明被反爬拦截，页面是营销页而非职位详情
BLOCK_HOST = "wow.liepin.com"
# 连续被拦这么多次就认定配额用尽，本轮不再试
BLOCK_THRESHOLD = 5

# 城市码 —— 逐个实测校验过返回结果的 dq 字段确实属于该城市
LIEPIN_CITIES = {
    "全国": "410",
    "北京": "010",
    "上海": "020",
    "广州": "050020",
    "深圳": "050090",
    "杭州": "070020",
    "南京": "060020",
    "苏州": "060080",
    "成都": "280020",
    "武汉": "170020",
    "西安": "270020",
    "天津": "030",
    "重庆": "040",
    "长沙": "180020",
}

# 移动端详情页 JD 正文容器
_JD_RE = re.compile(r'<div[^>]*class="[^"]*job-describe-duty[^"]*"[^>]*>(.*?)</div>', re.S)
# 移动端职位福利标签
_BENEFIT_RE = re.compile(r'<li[^>]*class="[^"]*job-benefits-item[^"]*"[^>]*>(.*?)</li>', re.S)


class LiepinCrawler(BaseCrawler):
    platform = "liepin"
    base_url = "https://www.liepin.com"
    min_delay = 1.0
    max_delay = 2.5

    def _default_headers(self) -> dict:
        h = super()._default_headers()
        h.update({
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Origin": "https://www.liepin.com",
            "Referer": "https://www.liepin.com/",
            "X-Client-Type": "web",
            "X-Fscp-Version": "1.1",
            "X-Fscp-Std-Info": '{"client_id": "40108"}',
            "X-Fscp-Trace-Id": "00000000-0000-0000-0000-000000000000",
            "X-Requested-With": "XMLHttpRequest",
        })
        return h

    def _detail_headers(self) -> dict:
        """详情页走移动端 —— PC 端会被重定向到营销页"""
        return {
            "User-Agent": MOBILE_UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": "https://m.liepin.com/",
            "Connection": "keep-alive",
        }

    @staticmethod
    def _search_body(keyword: str, city: str, page: int) -> dict:
        return {
            "data": {
                "mainSearchPcConditionForm": {
                    "city": city,
                    "dq": city,
                    "pubTime": "",
                    "currentPage": page,
                    "pageSize": 40,
                    "key": keyword,
                    "suggestTag": "",
                    "workYearCode": "0",
                    "compId": "",
                    "compName": "",
                    "compTag": "",
                    "industry": "",
                    "salary": "",
                    "jobKind": "",
                    "compScale": "",
                    "compKind": "",
                    "compStage": "",
                    "eduLevel": "",
                },
                "passThroughForm": {
                    "scene": "input",
                    "skeyword": keyword,
                    "sfrom": "search_job_pc",
                },
            }
        }

    async def crawl(
        self,
        keywords: List[str] = None,
        cities: List[str] = None,
        pages: int = 2,
        with_detail: bool = True,
    ) -> List[dict]:
        """抓取猎聘职位

        keywords: 岗位关键词，默认全量 JOB_KEYWORDS
        cities: 城市名列表，默认 ["全国"]
        pages: 每个关键词×城市抓几页（每页约 42 条）
        with_detail: 是否抓详情页补全 JD 正文
        """
        keywords = keywords or JOB_KEYWORDS
        cities = cities or ["全国"]
        all_jobs = []
        seen = set()

        for city_name in cities:
            city_code = LIEPIN_CITIES.get(city_name)
            if not city_code:
                logger.warning("liepin_unknown_city", extra={"city": city_name})
                continue

            for kw in keywords:
                for page in range(pages):
                    try:
                        jobs = await self._search(kw, city_code, page)
                    except Exception as e:
                        logger.warning(
                            "liepin_search_failed",
                            extra={"keyword": kw, "city": city_name, "page": page, "error": str(e)},
                        )
                        break

                    if not jobs:
                        break

                    new_count = 0
                    for job in jobs:
                        jid = job.get("platform_job_id", "")
                        if jid and jid not in seen:
                            seen.add(jid)
                            all_jobs.append(job)
                            new_count += 1

                    logger.info(
                        "liepin_crawl_page",
                        extra={"keyword": kw, "city": city_name, "page": page,
                               "fetched": len(jobs), "new": new_count},
                    )

        if with_detail and all_jobs:
            await self.fill_details(all_jobs)

        logger.info("liepin_crawl_done", extra={"total": len(all_jobs)})
        return all_jobs

    async def _search(self, keyword: str, city_code: str, page: int) -> List[dict]:
        """搜索单页"""
        resp = await self._post(LIEPIN_SEARCH_URL, json=self._search_body(keyword, city_code, page))
        result = resp.json()

        if result.get("flag") != 1:
            logger.warning(
                "liepin_api_error",
                extra={"flag": result.get("flag"), "msg": str(result.get("msg", ""))[:200]},
            )
            return []

        card_list = ((result.get("data") or {}).get("data") or {}).get("jobCardList") or []

        jobs = []
        for item in card_list:
            try:
                job = self._parse_card(item, keyword)
                if job:
                    jobs.append(job)
            except Exception as e:
                logger.debug("liepin_parse_item_failed", extra={"error": str(e)})
        return jobs

    def _parse_card(self, item: dict, keyword: str = "") -> Optional[dict]:
        """解析搜索结果卡片。真实字段藏在 item["job"] / item["comp"] 里。"""
        job = item.get("job") or {}
        comp = item.get("comp") or {}

        job_id = str(job.get("jobId") or "")
        title = job.get("title") or ""
        company = comp.get("compName") or ""
        if not job_id or not title or not company:
            return None

        # 公司属性作为标签：行业 / 规模 / 融资阶段
        tags = [t for t in (comp.get("compIndustry"), comp.get("compScale"), comp.get("compStage")) if t]
        # 岗位自带标签
        labels = job.get("labels")
        if isinstance(labels, list):
            tags.extend([str(x) for x in labels if x])
        if keyword:
            tags.append(keyword)

        return self.normalize_job({
            "job_id": job_id,
            "title": title,
            "company": company,
            "salary": job.get("salary") or "",
            "location": job.get("dq") or "",
            "experience": job.get("requireWorkYears") or "",
            "education": job.get("requireEduLevel") or "",
            "tags": tags[:6],
            "description": "",  # 列表接口不返回 JD，靠 _fill_details 补
            "requirements": [],
            "url": job.get("link") or f"https://www.liepin.com/job/{job_id}.shtml",
        })

    async def fill_details(self, jobs: List[dict], stop_on_block: bool = True) -> dict:
        """抓移动端详情页，就地补全每条 job 的 description / requirements / tags。

        详情页有 IP 级配额，一轮大概只能拿十几条，之后全部被重定向到营销页，
        且冷却几分钟也不恢复。所以默认连续撞墙 BLOCK_THRESHOLD 次就整批放弃，
        把配额留给下一轮 —— 硬扛只是白白发请求。

        jobs 里每项需要有 "url"；成功时就地写入 description/requirements/tags。
        """
        if not jobs:
            return {"ok": 0, "blocked": 0, "no_jd": 0, "error": 0, "skipped": 0}

        stats = {"ok": 0, "blocked": 0, "no_jd": 0, "error": 0, "skipped": 0}
        consecutive_block = 0
        give_up = False

        headers = self._detail_headers()
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(30.0), follow_redirects=True, headers=headers
        ) as client:
            for job in jobs:
                if give_up:
                    stats["skipped"] += 1
                    continue

                url = job.get("url")
                if not url:
                    stats["skipped"] += 1
                    continue

                m_url = url.replace("www.liepin.com", "m.liepin.com")
                try:
                    await self._sleep()
                    resp = await client.get(m_url)

                    if resp.status_code != 200:
                        stats["error"] += 1
                        continue

                    if BLOCK_HOST in str(resp.url):
                        stats["blocked"] += 1
                        consecutive_block += 1
                        if stop_on_block and consecutive_block >= BLOCK_THRESHOLD:
                            give_up = True
                            logger.warning(
                                "liepin_detail_quota_exhausted",
                                extra={"after": stats["ok"], "threshold": BLOCK_THRESHOLD},
                            )
                        continue

                    consecutive_block = 0
                    html = resp.text

                    m = _JD_RE.search(html)
                    if not m:
                        stats["no_jd"] += 1
                        continue

                    desc = self.html_to_text(m.group(1))
                    desc = re.sub(r"\n?查看全部\s*$", "", desc).strip()
                    if not desc:
                        stats["no_jd"] += 1
                        continue

                    job["description"] = desc[:5000]
                    job["requirements"] = self.extract_requirements(desc)
                    stats["ok"] += 1

                    benefits = [self.html_to_text(b) for b in _BENEFIT_RE.findall(html)[:4]]
                    existing_tags = job.get("tags") or []
                    benefits = [b for b in benefits if b and b not in existing_tags]
                    if benefits:
                        job["tags"] = (existing_tags + benefits)[:8]
                except Exception as e:
                    stats["error"] += 1
                    logger.debug("liepin_detail_failed", extra={"url": m_url, "error": str(e)})

        logger.info("liepin_detail_done", extra={"total": len(jobs), **stats})
        return stats
