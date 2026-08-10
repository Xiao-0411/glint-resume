"""
职位爬虫基类 —— 定义公共接口和工具方法
"""
import asyncio
import logging
import random
import re
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

# 技能关键词库 —— 从 JD 正文中提取结构化技能标签
SKILL_PATTERNS = [
    # 编程语言
    "Java", "Python", "Golang", "Go语言", "C\\+\\+", "C#", "JavaScript", "TypeScript",
    "Rust", "Kotlin", "Swift", "PHP", "Scala", "Shell",
    # 后端框架 / 中间件
    "Spring Cloud", "Spring Boot", "Spring", "MyBatis", "Django", "Flask", "FastAPI",
    "Dubbo", "gRPC", "RabbitMQ", "RocketMQ", "Kafka", "Nginx", "Netty",
    # 前端
    "Vue", "React", "Angular", "Node\\.js", "Webpack", "Vite", "小程序", "Flutter",
    "HTML5", "CSS3", "uni-app",
    # 数据 / 存储
    "MySQL", "Redis", "MongoDB", "PostgreSQL", "Oracle", "Elasticsearch",
    "ClickHouse", "Hadoop", "Hive", "Spark", "Flink", "HBase", "数据仓库", "ETL",
    # 云原生 / 运维
    "Docker", "Kubernetes", "K8s", "Linux", "Git", "Jenkins", "CI/CD",
    "AWS", "Azure", "阿里云", "腾讯云", "微服务", "分布式", "高并发",
    # 算法 / AI
    "机器学习", "深度学习", "NLP", "自然语言处理", "计算机视觉", "推荐系统",
    "TensorFlow", "PyTorch", "大模型", "LLM", "RAG", "AIGC", "强化学习",
    # 测试
    "自动化测试", "性能测试", "接口测试", "Selenium", "JMeter", "Appium", "Pytest",
    # 产品 / 设计 / 运营
    "产品设计", "需求分析", "用户研究", "竞品分析", "数据分析", "项目管理",
    "Figma", "Axure", "Sketch", "PRD", "SQL", "Excel", "Tableau", "Power BI",
    "UI设计", "交互设计", "用户体验", "用户增长", "私域运营", "内容运营",
    "活动策划", "社群运营", "SEO", "SEM", "投放优化",
    # 通用职能
    "敏捷开发", "Scrum", "英语", "沟通能力", "团队协作",
]

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\n{2,}")


class BaseCrawler(ABC):
    """爬虫基类"""

    platform: str = "unknown"
    base_url: str = ""
    # 请求间隔（秒），子类可覆盖
    min_delay: float = 1.5
    max_delay: float = 4.0

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

    async def _sleep(self):
        await asyncio.sleep(random.uniform(self.min_delay, self.max_delay))

    async def _get(self, url: str, **kwargs) -> httpx.Response:
        client = await self._get_client()
        await self._sleep()
        resp = await client.get(url, **kwargs)
        resp.raise_for_status()
        return resp

    async def _post(self, url: str, **kwargs) -> httpx.Response:
        client = await self._get_client()
        await self._sleep()
        resp = await client.post(url, **kwargs)
        resp.raise_for_status()
        return resp

    @abstractmethod
    async def crawl(self, keywords: List[str] = None) -> List[dict]:
        """抓取职位列表，返回标准化 dict 列表"""
        ...

    @staticmethod
    def html_to_text(html: str) -> str:
        """把 JD 的 HTML 片段转成纯文本"""
        if not html:
            return ""
        text = html.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
        text = _TAG_RE.sub("\n", text)
        text = text.replace("&nbsp;", " ").replace("&amp;", "&")
        text = text.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
        lines = [ln.strip() for ln in text.split("\n")]
        return _WS_RE.sub("\n", "\n".join(ln for ln in lines if ln)).strip()

    @staticmethod
    def extract_requirements(desc: str, limit: int = 12) -> List[str]:
        """从职位描述中提取技能关键词"""
        if not desc:
            return []
        found = []
        for pattern in SKILL_PATTERNS:
            if re.search(pattern, desc, re.IGNORECASE):
                skill = pattern.replace("\\", "")
                if skill not in found:
                    found.append(skill)
        return found[:limit]

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
