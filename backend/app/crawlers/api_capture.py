"""被动捕获招聘平台前端自身发出的搜索接口响应。

思路来自 boss-zhipin-scraper skill：BOSS直聘等平台对列表页薪资做了字体反爬，
从 DOM 里读到的薪资是乱码字形；但页面自己调用的 JSON 接口返回的是明文
`salaryDesc`。我们不去伪造请求（缺少 __zp_stoken__ 等签名参数必然失败），
而是让已登录的浏览器正常访问搜索页，再从 network 事件里把它自己发出的
响应体捞出来解析。

因此本模块只做两件事：
1. 监听 page 的 response 事件，缓存目标接口的 JSON 响应；
2. 把各平台的原始字段映射成项目统一的 job 结构。

登录态始终留在本机浏览器 profile 里，这里不读取也不上传任何 Cookie。
"""
import asyncio
import itertools
import json
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import quote

from playwright.async_api import Page, Response

logger = logging.getLogger("glint.crawler.capture")

# 各平台搜索接口路径特征（子串匹配即可，平台常带不同 query 前缀）。
# 每个平台给多个候选：平台改接口路径时不至于直接失效，命中任一个即可。
# 只有 zhipin 那条是从 boss-zhipin-scraper 确认过的；另两条来自项目原有代码，
# 若某平台一直「未捕获到响应」，用 F12 Network 看真实路径后补进对应列表。
API_PATH_CANDIDATES = {
    "zhipin": (
        "/wapi/zpgeek/search/joblist.json",
        "/wapi/zpgeek/pc/recommend/job/list.json",
        "/wapi/zpgeek/search/joblist",
    ),
    "zhaopin": (
        "/c/i/search/positions",
        "/c/i/sou",
        "/search/positions",
        "fe-api.zhaopin.com/c/i/",
    ),
    "liepin": (
        "searchfront4c.pc-search-job",
        "/api/com.liepin.searchfront4c.pc-search-job",
        "com.liepin.searchfront4c",
        "/api/com.liepin.searchfront4c",
    ),
}

# 兼容旧引用：取每个平台的首选路径
API_PATHS = {p: c[0] for p, c in API_PATH_CANDIDATES.items()}


def matches_api_path(platform: str, url: str) -> bool:
    """URL 是否命中该平台的搜索接口（任一候选路径即可）。"""
    return any(path in url for path in API_PATH_CANDIDATES.get(platform, ()))

# 搜索页 URL 模板。zhipin 用 /web/geek/job（支持 page 翻页参数）
SEARCH_URLS = {
    "zhipin": "https://www.zhipin.com/web/geek/job?query={keyword}&city={city}&page={page}",
    "zhaopin": "https://www.zhaopin.com/sou/?kw={keyword}&p={page}",
    "liepin": "https://www.liepin.com/zhaopin/?key={keyword}&currentPage={page}",
}

# 全国。需要限定城市时传 101010100(北京) / 101020100(上海) 等 9 位编码
CITY_NATIONWIDE = "100010000"

# BOSS 已知风控码。码表会随平台策略变化，所以再按 message 关键字兜底，
# 避免新风控码被当成普通错误、进而误报成「未登录」。
RESTRICTED_CODES = {31, 37}
RESTRICTED_MESSAGE_KEYWORDS = (
    "环境存在异常", "访问频繁", "操作太频繁", "安全校验", "滑块", "验证",
)
# 业务成功码：BOSS/猎聘用 0，智联部分接口用 200
SUCCESS_CODES = {0, 200}


class ProbeStatus(str, Enum):
    """一次搜索响应的判定结果，用于区分「没数据」和「被拦截」。"""
    AVAILABLE = "available"          # 正常返回职位
    EMPTY = "empty"                  # 接口通了但确实没有匹配职位
    UNAUTHENTICATED = "unauth"       # 登录态失效
    RESTRICTED = "restricted"        # 风控 / 限流 / 需要验证
    RESPONSE_ERROR = "error"         # 其它异常响应


@dataclass
class ProbeResult:
    status: ProbeStatus
    code: Optional[int] = None
    message: str = ""
    jobs: List[dict] = field(default_factory=list)

    @property
    def blocked(self) -> bool:
        return self.status in (ProbeStatus.UNAUTHENTICATED, ProbeStatus.RESTRICTED)

    def describe(self) -> str:
        label = {
            ProbeStatus.AVAILABLE: "正常",
            ProbeStatus.EMPTY: "接口返回 0 条职位",
            ProbeStatus.UNAUTHENTICATED: "登录态失效，请在浏览器中重新登录",
            ProbeStatus.RESTRICTED: "被平台风控拦截，请在浏览器中完成验证后再试",
            ProbeStatus.RESPONSE_ERROR: "接口响应异常",
        }[self.status]
        detail = self.message.strip()
        if self.code is not None:
            detail = f"code={self.code} {detail}".strip()
        return f"{label}（{detail}）" if detail else label


class ResponseCapture:
    """挂在 Page 上，持续把目标接口的 JSON 响应推进队列。

    handler 是 fire-and-forget 的异步任务，读 body 需要一次驱动往返，
    所以 drain() 之前触发的响应可能在 drain() 之后才入队。用 epoch 计数区分：
    每次 drain() 递增 epoch，wait_next 只接受当前 epoch 的响应，
    避免上一个关键词的结果被当成本次导航的结果。
    """

    def __init__(self, page: Page, platform: str):
        self.page = page
        self.platform = platform
        self.path = API_PATHS[platform]
        self._queue: asyncio.Queue = asyncio.Queue()
        self._handler: Optional[Callable] = None
        self._epoch_counter = itertools.count()
        self._epoch = next(self._epoch_counter)

    def attach(self) -> None:
        async def on_response(response: Response) -> None:
            if not matches_api_path(self.platform, response.url):
                return
            epoch = self._epoch  # 记录响应发生时所属的轮次
            try:
                # 必须在这里立刻读 body：导航之后响应体可能已被释放
                body = await response.body()
            except Exception as exc:  # 页面跳转/连接关闭都可能触发
                logger.debug("capture_body_failed", extra={"platform": self.platform, "error": str(exc)})
                return
            try:
                data = json.loads(body.decode("utf-8", errors="replace"))
            except (json.JSONDecodeError, ValueError):
                logger.debug("capture_not_json", extra={"platform": self.platform, "url": response.url[:200]})
                return
            await self._queue.put((epoch, response.status, data))

        self._handler = on_response
        self.page.on("response", on_response)

    def detach(self) -> None:
        if self._handler is not None:
            try:
                self.page.remove_listener("response", self._handler)
            except Exception:
                pass
            self._handler = None

    def drain(self) -> None:
        """开启新一轮：丢弃已入队的旧响应，并让在途的旧响应失效。"""
        self._epoch = next(self._epoch_counter)
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    async def wait_next(self, timeout: float = 25.0) -> Optional[tuple]:
        """等待本轮的下一个目标接口响应，超时返回 None。"""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                return None
            try:
                epoch, status, data = await asyncio.wait_for(self._queue.get(), timeout=remaining)
            except asyncio.TimeoutError:
                return None
            if epoch != self._epoch:
                # 上一轮遗留的在途响应，丢弃后继续等
                continue
            return status, data


# ============================================================
# 响应判定
# ============================================================
def classify(platform: str, http_status: int, data: Any) -> ProbeResult:
    """把一次响应判定成 可用/空/未登录/风控/异常，不要塌缩成一个 bool。"""
    if http_status == 401:
        return ProbeResult(ProbeStatus.UNAUTHENTICATED, message="HTTP 401")
    if http_status in (403, 429):
        return ProbeResult(ProbeStatus.RESTRICTED, message=f"HTTP {http_status}")
    if http_status != 200:
        return ProbeResult(ProbeStatus.RESPONSE_ERROR, message=f"HTTP {http_status}")
    if not isinstance(data, dict):
        return ProbeResult(ProbeStatus.RESPONSE_ERROR, message="响应不是 JSON 对象")

    raw_code = data.get("code")
    try:
        code = int(raw_code) if raw_code is not None else None
    except (TypeError, ValueError):
        code = None
    message = str(data.get("message") or data.get("msg") or "")

    # 先按 message 关键字识别风控，这对所有平台都适用
    if any(kw in message for kw in RESTRICTED_MESSAGE_KEYWORDS):
        return ProbeResult(ProbeStatus.RESTRICTED, code=code, message=message)
    if platform == "zhipin" and code in RESTRICTED_CODES:
        return ProbeResult(ProbeStatus.RESTRICTED, code=code, message=message)
    # 业务码非 0 说明接口本身失败了，不能当成「没有匹配职位」
    if code is not None and code not in SUCCESS_CODES:
        return ProbeResult(ProbeStatus.RESPONSE_ERROR, code=code, message=message)

    jobs = MAPPERS[platform](data)
    if jobs:
        return ProbeResult(ProbeStatus.AVAILABLE, code=code, message=message, jobs=jobs)
    return ProbeResult(ProbeStatus.EMPTY, code=code, message=message)


# ============================================================
# 各平台字段映射
# ============================================================
def _join(*parts: str, sep: str = "·") -> str:
    return sep.join(p for p in parts if p)


def _dig(data: dict, *paths: tuple) -> list:
    """按多组候选路径找列表，兼容平台字段改名。"""
    for path in paths:
        node: Any = data
        for key in path:
            if not isinstance(node, dict):
                node = None
                break
            node = node.get(key)
        if isinstance(node, list) and node:
            return node
    return []


def map_zhipin(data: dict) -> List[dict]:
    items = _dig(data, ("zpData", "jobList"), ("zpData", "joblist"), ("zpData", "list"))
    jobs = []
    for raw in items:
        if not isinstance(raw, dict):
            continue
        job_id = str(raw.get("encryptJobId") or raw.get("jobId") or "")
        if not job_id:
            continue
        brand_id = str(raw.get("encryptBrandId") or "")
        skills = [s for s in (raw.get("skills") or []) if s]
        labels = [s for s in (raw.get("jobLabels") or []) if s]
        welfare = [s for s in (raw.get("welfareList") or []) if s]
        jobs.append({
            "platform": "zhipin",
            "platform_job_id": job_id[:128],
            "title": str(raw.get("jobName") or "")[:256],
            "company": str(raw.get("brandName") or "未知公司")[:256],
            # 接口直接给明文薪资，不经过前端字体映射
            "salary": str(raw.get("salaryDesc") or "")[:64],
            "location": _join(
                str(raw.get("cityName") or ""),
                str(raw.get("areaDistrict") or ""),
                str(raw.get("businessDistrict") or ""),
            )[:128],
            "experience": str(raw.get("jobExperience") or "")[:64],
            "education": str(raw.get("jobDegree") or "")[:64],
            "tags": (labels + welfare)[:12],
            "description": _join(
                str(raw.get("brandIndustry") or ""),
                str(raw.get("brandScaleName") or ""),
                str(raw.get("brandStageName") or ""),
                sep=" | ",
            ),
            "requirements": skills[:20],
            "url": f"https://www.zhipin.com/job_detail/{job_id}.html" if brand_id or job_id else "",
            "salary_source": "api",
        })
    return jobs


def _text(value: Any) -> str:
    """把可能是 str / dict / None 的字段安全转成字符串。"""
    if value is None:
        return ""
    if isinstance(value, dict):
        for key in ("name", "value", "label", "text"):
            if value.get(key):
                return str(value[key])
        return ""
    return str(value)


def map_zhaopin(data: dict) -> List[dict]:
    items = _dig(data, ("data", "list"), ("data", "positionList"), ("data", "results"))
    jobs = []
    for raw in items:
        if not isinstance(raw, dict):
            continue
        job_id = str(raw.get("number") or raw.get("jobNumber") or raw.get("positionId") or "")
        if not job_id:
            continue
        skill_nodes = raw.get("skillLabel") or raw.get("jobKnowledgeSkills") or []
        skills = [_text(s) for s in skill_nodes]
        welfare = [_text(w) for w in (raw.get("welfareLabel") or raw.get("welfareTagList") or [])]
        city = _text(raw.get("workCity") or raw.get("cityDistrict"))
        # company 可能是字符串也可能是对象，两种都要兼容
        company = _text(raw.get("companyName")) or _text(raw.get("company")) or "未知公司"
        jobs.append({
            "platform": "zhaopin",
            "platform_job_id": job_id[:128],
            "title": _text(raw.get("name") or raw.get("jobName"))[:256],
            "company": company[:256],
            "salary": _text(raw.get("salary") or raw.get("salaryReal"))[:64],
            "location": _join(city, _text(raw.get("businessArea")))[:128],
            "experience": _text(raw.get("workingExp") or raw.get("workingExpLabel"))[:64],
            "education": _text(raw.get("education") or raw.get("educationLabel"))[:64],
            "tags": [s for s in welfare if s][:12],
            "description": _text(raw.get("jobSummary"))[:4000],
            "requirements": [s for s in skills if s][:20],
            "url": _text(raw.get("positionURL") or raw.get("jobUrl"))[:512],
            "salary_source": "api",
        })
    return jobs


def map_liepin(data: dict) -> List[dict]:
    items = _dig(
        data,
        ("data", "data", "jobCardList"),
        ("data", "jobCardList"),
        ("data", "data", "jobList"),
        ("data", "list"),
    )
    jobs = []
    for raw in items:
        if not isinstance(raw, dict):
            continue
        # 猎聘把职位字段包在 job 子对象里，同时也有平铺的老结构
        node = raw.get("job") if isinstance(raw.get("job"), dict) else raw
        comp = raw.get("comp") if isinstance(raw.get("comp"), dict) else {}
        link = _text(node.get("link") or node.get("jobUrl"))
        # 只用真正的职位标识；refreshTime 之类的字段多个职位会重复，
        # 当成 ID 会让不同职位互相覆盖成同一行。
        job_id = _text(node.get("jobId") or node.get("encryptJobId"))
        if not job_id and link:
            # 从链接里取 /job/12345.shtml 这段作为稳定标识
            match = re.search(r"/(?:job|a)/([A-Za-z0-9_~-]+)", link)
            job_id = match.group(1) if match else link
        if not job_id:
            continue
        labels = [_text(t) for t in (node.get("labels") or node.get("jobLabels") or [])]
        labels = [t for t in labels if t]
        jobs.append({
            "platform": "liepin",
            "platform_job_id": job_id[:128],
            "title": _text(node.get("title") or node.get("jobTitle"))[:256],
            "company": (_text(comp.get("compName")) or _text(node.get("compName")) or "未知公司")[:256],
            "salary": _text(node.get("salary"))[:64],
            "location": _text(node.get("dq") or node.get("city"))[:128],
            "experience": _text(node.get("requireWorkYears"))[:64],
            "education": _text(node.get("requireEduLevel"))[:64],
            "tags": labels[:12],
            "description": _join(
                _text(comp.get("compIndustry")), _text(comp.get("compScale")), sep=" | "
            ),
            "requirements": labels[:20],
            "url": link[:512],
            "salary_source": "api",
        })
    return jobs


MAPPERS: Dict[str, Callable[[dict], List[dict]]] = {
    "zhipin": map_zhipin,
    "zhaopin": map_zhaopin,
    "liepin": map_liepin,
}


def build_search_url(platform: str, keyword: str, page: int = 1, city: str = CITY_NATIONWIDE) -> str:
    return SEARCH_URLS[platform].format(keyword=quote(keyword), page=page, city=city)
