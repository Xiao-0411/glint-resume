"""
职位爬虫基类 —— 定义公共接口和工具方法
"""
import asyncio
import logging
import random
from abc import ABC, abstractmethod
from typing import List, Optional

import httpx

logger = logging.getLogger("glint.crawler")

# 常用 User-Agent 池
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
]

# 岗位关键词（全量抓取覆盖各方向）
JOB_KEYWORDS = [
    "产品经理", "Java开发", "前端开发", "后端开发", "数据分析",
    "测试工程师", "运营", "Python开发", "C++开发", "算法工程师",
    "UI设计", "iOS开发", "Android开发", "运维工程师", "架构师",
    "项目经理", "人力资源", "财务", "市场营销", "销售",
    "人工智能", "大数据", "网络安全", "嵌入式", "游戏策划",
    "产品运营", "新媒体运营", "电商运营", "技术支持", "实习生",
]


class BaseCrawler(ABC):
    """爬虫基类"""

    platform: str = "unknown"
    base_url: str = ""

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0),
                follow_redirects=True,
                headers=self._default_headers(),
            )
        return self._client

    def _default_headers(self) -> dict:
        return {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Cache-Control": "max-age=0",
        }

    async def _get(self, url: str, **kwargs) -> httpx.Response:
        client = await self._get_client()
        delay = random.uniform(1.5, 4.0)
        await asyncio.sleep(delay)
        resp = await client.get(url, **kwargs)
        resp.raise_for_status()
        return resp

    @abstractmethod
    async def crawl(self, keywords: List[str] = None) -> List[dict]:
        """抓取职位列表，返回标准化 dict 列表"""
        ...

    def normalize_job(self, raw: dict) -> dict:
        """标准化为统一格式：
        {
            "platform": str,
            "platform_job_id": str,
            "title": str,
            "company": str,
            "salary": str,
            "location": str,
            "experience": str,
            "education": str,
            "tags": [str],
            "description": str,
            "requirements": [str],
            "url": str,
        }
        """
        return {
            "platform": self.platform,
            "platform_job_id": str(raw.get("job_id", raw.get("id", ""))),
            "title": str(raw.get("title", raw.get("job_name", ""))),
            "company": str(raw.get("company", raw.get("company_name", ""))),
            "salary": str(raw.get("salary", raw.get("salary_range", ""))),
            "location": str(raw.get("location", raw.get("city", raw.get("area", "")))),
            "experience": str(raw.get("experience", raw.get("exp", ""))),
            "education": str(raw.get("education", raw.get("edu", ""))),
            "tags": raw.get("tags", []) if isinstance(raw.get("tags"), list) else [],
            "description": str(raw.get("description", raw.get("desc", ""))),
            "requirements": raw.get("requirements", []) if isinstance(raw.get("requirements"), list) else [],
            "url": str(raw.get("url", "")),
        }

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None