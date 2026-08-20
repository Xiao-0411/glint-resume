"""
职位爬虫基类 —— 定义公共接口和工具方法
"""
import asyncio

from app.core.logging_config import get_logger
import os
import random
from abc import ABC, abstractmethod
from typing import List, Optional

import httpx

logger = get_logger("glint.crawler")

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

DEFAULT_CRAWLER_CITIES = ["北京", "上海", "广州", "深圳", "杭州", "成都", "武汉", "西安"]

# 招聘供给高度集中的城市，排在全量池最前面，
# 保证冷启动阶段用户最可能搜索的城市先有数据。
PRIORITY_CITIES = [
    "北京", "上海", "广州", "深圳", "杭州", "成都", "武汉", "西安",
    "南京", "苏州", "天津", "重庆", "长沙", "郑州", "青岛", "宁波",
    "合肥", "东莞", "佛山", "厦门", "福州", "济南", "无锡", "大连",
]


def select_keywords(keywords: List[str] = None) -> List[str]:
    """选择本轮抓取的关键词。

    显式传入（用户实时搜索）时原样返回。定时抓取时关键词跟随城市游标推进：
    只有当城市列表走完一整圈，关键词才前进一格，从而覆盖全部「城市 × 关键词」组合。
    """
    if keywords is not None:
        return keywords
    raw_limit = os.getenv("CRAWLER_MAX_KEYWORDS", "5")
    try:
        limit = int(raw_limit)
    except ValueError as exc:
        raise RuntimeError("CRAWLER_MAX_KEYWORDS 必须是整数") from exc
    if not 1 <= limit <= len(JOB_KEYWORDS):
        raise RuntimeError(f"CRAWLER_MAX_KEYWORDS 必须在 1 到 {len(JOB_KEYWORDS)} 之间")

    from app.crawlers.cursor import city_cycles, slice_at

    # 用城市已完成的圈数决定关键词偏移，关键词游标本身不独立推进。
    offset = city_cycles() * limit
    return slice_at(JOB_KEYWORDS, offset, limit)


def all_crawl_cities() -> List[str]:
    """全量抓取的城市池：默认取 373 城市表，可用 CRAWLER_CITIES 覆盖。

    热门城市排在最前，其余按字典序，使同省城市相邻、进度易于观察。
    """
    raw = os.getenv("CRAWLER_CITIES", "").strip()
    if raw:
        selected = [city.strip() for city in raw.split(",") if city.strip()]
        if selected:
            return selected

    from app.services.location_catalog import all_city_names

    catalog = set(all_city_names())
    head = [city for city in PRIORITY_CITIES if city in catalog]
    tail = sorted(catalog - set(head))
    return head + tail


def select_cities(cities: List[str] = None) -> List[str]:
    """选择本轮抓取的城市。

    显式传入（用户实时搜索）时原样返回；定时抓取则从持久化游标取下一个切片。
    """
    if cities is not None:
        return [city.strip() for city in cities if city and city.strip()]

    pool = all_crawl_cities()
    try:
        limit = int(os.getenv("CRAWLER_MAX_CITIES", "4"))
    except ValueError as exc:
        raise RuntimeError("CRAWLER_MAX_CITIES 必须是整数") from exc
    if not 1 <= limit <= len(pool):
        raise RuntimeError(f"CRAWLER_MAX_CITIES 必须在 1 到 {len(pool)} 之间")

    from app.crawlers.cursor import next_slice

    return next_slice("city", pool, limit)


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
        last_error = None
        for attempt in range(2):
            try:
                resp = await client.get(url, **kwargs)
                resp.raise_for_status()
                return resp
            except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as exc:
                last_error = exc
                if attempt == 0:
                    await asyncio.sleep(1.0)
        raise last_error

    @abstractmethod
    async def crawl(self, keywords: List[str] = None, cities: List[str] = None) -> List[dict]:
        """抓取职位列表，返回标准化 dict 列表"""
        ...

    async def fetch_detail(self, job: dict) -> dict:
        """按需抓取单个岗位详情；不支持的平台返回空字典。"""
        return {}

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
