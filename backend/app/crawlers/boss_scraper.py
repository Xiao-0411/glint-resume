"""BOSS直聘 采集：改为调用 boss-zhipin-scraper 的原生 CDP 脚本。

为什么不再用 Playwright 连 BOSS：
Playwright 的 connect_over_cdp 在连上的瞬间会对**所有**已打开标签页下发
Runtime.enable / Page.enable / Target.setAutoAttach（playwright-core 内部
硬编码，没有开关），并且我们试过的可见性伪装 + 焦点仿真也没能挡住 BOSS 的
风控——表现就是会话被踢回 /web/user/ 登录页。

vendor/boss_zhipin_scraper 的脚本走的是另一条路：
- 自己开一个独立的 Chrome（独立 profile，不碰你日常浏览器的登录态）
- 手写 CDP，只用 Page.navigate / Network.enable / Network.getResponseBody，
  不下发 Runtime.enable，暴露面小得多
- 同样是被动捕获页面自身的 joblist.json 响应，拿明文 salaryDesc

因此这里把 BOSS 交给它，用子进程调用 + 读它写出的 JSON，再映射成项目内部
统一的 job 结构。智联/猎聘仍走 browser_session.py 的 Playwright 路径。

上游脚本 MIT 许可，见 vendor/boss_zhipin_scraper/LICENSE。
"""
import asyncio
import json
import logging
import os
import re
import sys
from typing import Dict, List, Optional

logger = logging.getLogger("glint.crawler.boss")

_HERE = os.path.dirname(os.path.abspath(__file__))
VENDOR_DIR = os.path.normpath(os.path.join(_HERE, "..", "..", "vendor", "boss_zhipin_scraper"))
SCRIPT_PATH = os.path.join(VENDOR_DIR, "scripts", "boss_cdp_raw.py")


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, ""))
    except (TypeError, ValueError):
        return default


# 抓取参数。上游脚本单次上限 10 页（每页 30 条），翻页间隔 12-22 秒随机，
# 不要为了快而调高——防封号。
PAGES_PER_KEYWORD = _env_int("BOSS_PAGES_PER_KEYWORD", 2)
CDP_PORT = _env_int("BOSS_CDP_PORT", 9333)
DEFAULT_CITY = os.getenv("BOSS_CITY", "全国")
# 每个关键词的超时：翻页间隔最坏 22s/页，再留出导航和启动余量
KEYWORD_TIMEOUT = _env_int("BOSS_KEYWORD_TIMEOUT", 60 + PAGES_PER_KEYWORD * 45)
SETUP_TIMEOUT = _env_int("BOSS_SETUP_TIMEOUT", 360)


class BossLoginRequired(RuntimeError):
    """专用浏览器未登录 BOSS —— 需要人工在弹出的窗口里登录一次。"""


class BossBlocked(RuntimeError):
    """被 BOSS 风控拦截，应停止本轮抓取。"""


def _python_executable() -> str:
    return sys.executable or "python"


async def _run_script(args: List[str], timeout: int) -> tuple:
    """跑一次 vendor 脚本，返回 (returncode, stdout, stderr)。"""
    cmd = [_python_executable(), SCRIPT_PATH, *args]
    env = dict(os.environ)
    # 上游脚本大量 print 中文，Windows 控制台默认 GBK 会抛 UnicodeEncodeError
    env["PYTHONIOENCODING"] = "utf-8"
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=VENDOR_DIR,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise RuntimeError(f"boss_cdp_raw.py 超时（{timeout}s）: {' '.join(args)}")
    return (
        proc.returncode,
        (out or b"").decode("utf-8", errors="replace"),
        (err or b"").decode("utf-8", errors="replace"),
    )


def _classify_output(text: str) -> Optional[Exception]:
    """从脚本输出里识别登录/风控失败，转成明确的异常。"""
    if "未检测到 BOSS直聘登录状态" in text or "未登录" in text:
        return BossLoginRequired(
            "BOSS 专用浏览器未登录。请运行 启动BOSS登录.bat，在弹出的窗口里登录 zhipin.com 后重试"
        )
    for marker in ("风控", "环境存在异常", "访问频繁", "操作太频繁", "安全校验", "滑块"):
        if marker in text:
            return BossBlocked(f"BOSS 风控拦截：{marker}。请稍后再试，或在专用浏览器里完成验证")
    return None


class BossScraperCollector:
    """用 vendor 脚本采集 BOSS，接口对齐 BrowserSessionCollector 的用法。"""

    def __init__(self, city: str = ""):
        self.city = city or DEFAULT_CITY
        self.errors: Dict[str, str] = {}
        self.warnings: Dict[str, List[str]] = {}
        self.blocked: Dict[str, bool] = {}
        self._ready = False

    @staticmethod
    def available() -> bool:
        return os.path.isfile(SCRIPT_PATH)

    async def check(self) -> bool:
        """环境自检：依赖 / CDP 连通性 / 登录态。"""
        code, out, err = await _run_script(["--check", "--cdp-port", str(CDP_PORT)], timeout=90)
        text = out + err
        logger.info("boss_check", extra={"returncode": code})
        return code == 0 and "未登录" not in text

    async def start_and_wait_for_login(self) -> None:
        """确保专用 Chrome 已起且已登录；未就绪时拉起并等待人工登录。"""
        if not self.available():
            raise RuntimeError(f"找不到 vendor 脚本: {SCRIPT_PATH}")

        if await self.check():
            self._ready = True
            logger.info("boss_session_ready", extra={"mode": "existing"})
            print("BOSS 专用浏览器已就绪（已登录）。", flush=True)
            return

        print(
            "BOSS 专用浏览器未就绪，正在拉起独立 Chrome。\n"
            "如果弹出窗口要求登录，请在该窗口里登录 zhipin.com，脚本会自动等待登录完成。",
            flush=True,
        )
        code, out, err = await _run_script(
            ["--setup-chrome", "--cdp-port", str(CDP_PORT)], timeout=SETUP_TIMEOUT
        )
        text = out + err
        if code != 0:
            exc = _classify_output(text)
            if exc:
                raise exc
            tail = "\n".join(text.strip().splitlines()[-6:])
            raise RuntimeError(f"BOSS 专用浏览器启动失败（exit {code}）:\n{tail}")
        self._ready = True
        logger.info("boss_session_ready", extra={"mode": "setup"})

    async def crawl(self, keywords: List[str]) -> List[dict]:
        """逐个关键词抓取并映射成项目统一结构。"""
        if not self._ready:
            await self.start_and_wait_for_login()

        collected: List[dict] = []
        seen = set()
        for keyword in keywords:
            try:
                jobs = await self._crawl_keyword(keyword)
            except (BossLoginRequired, BossBlocked) as exc:
                # 登录失效/风控：立即停止，保留已抓到的数据
                self.blocked["zhipin"] = True
                self.errors["zhipin"] = str(exc)[:1000]
                logger.warning("boss_stop", extra={"keyword": keyword, "error": str(exc)})
                break
            except Exception as exc:
                self.warnings.setdefault("zhipin", []).append(f"{keyword}: {str(exc)[:200]}")
                logger.warning("boss_keyword_failed", extra={"keyword": keyword, "error": str(exc)})
                continue
            for job in jobs:
                jid = job["platform_job_id"]
                if jid and jid not in seen:
                    seen.add(jid)
                    collected.append(job)

        warns = self.warnings.get("zhipin", [])
        if not collected and warns and not self.blocked.get("zhipin"):
            self.errors.setdefault("zhipin", f"全部关键词抓取失败，例如 {warns[0]}")
        return collected

    async def _crawl_keyword(self, keyword: str) -> List[dict]:
        out_path = os.path.join(VENDOR_DIR, ".out", f"jobs_{_slug(keyword)}.json")
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        if os.path.exists(out_path):
            os.remove(out_path)  # 别把上次的结果当成这次的

        code, out, err = await _run_script(
            [
                "--keyword", keyword,
                "--city", self.city,
                "--pages", str(PAGES_PER_KEYWORD),
                "--no-detail",          # 详情页每条 10-25 秒，全量抓取时太慢
                "--output", out_path,
                "--cdp-port", str(CDP_PORT),
            ],
            timeout=KEYWORD_TIMEOUT,
        )
        text = out + err
        exc = _classify_output(text)
        if exc:
            raise exc
        if code != 0 and not os.path.exists(out_path):
            tail = "\n".join(text.strip().splitlines()[-5:])
            raise RuntimeError(f"抓取失败（exit {code}）: {tail}")

        return _load_and_map(out_path)


def _slug(keyword: str) -> str:
    """关键词转成安全的文件名片段（中文直接保留，去掉路径分隔符等）。"""
    return re.sub(r"[^\w一-鿿-]+", "_", keyword).strip("_") or "kw"


def _load_and_map(path: str) -> List[dict]:
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            payload = json.load(f)
    except (json.JSONDecodeError, OSError, ValueError) as exc:
        logger.warning("boss_output_unreadable", extra={"path": path, "error": str(exc)})
        return []
    raw_jobs = payload.get("jobs") if isinstance(payload, dict) else None
    if not isinstance(raw_jobs, list):
        return []
    return [j for j in (map_scraper_job(r) for r in raw_jobs) if j]


def map_scraper_job(raw: dict) -> Optional[dict]:
    """把 vendor 脚本的输出条目映射成项目内部的 job 结构。"""
    if not isinstance(raw, dict):
        return None

    link = str(raw.get("job_link") or "")
    # 优先用职位详情页 id 作为稳定标识；脚本的 job_id 是 link 的哈希，也可用
    match = re.search(r"/job_detail/([A-Za-z0-9_~-]+)", link)
    job_id = match.group(1) if match else str(raw.get("job_id") or "")
    if not job_id:
        return None

    # tags 形如 "5-10年 | 本科"，拆出经验和学历
    tags_text = str(raw.get("tags") or "")
    parts = [p.strip() for p in tags_text.split("|") if p.strip()]
    experience = next((p for p in parts if re.search(r"年|应届|在校|经验", p)), "")
    education = next(
        (p for p in parts if re.search(r"本科|硕士|博士|大专|高中|中专|初中|学历", p)), ""
    )

    skills = [s.strip() for s in str(raw.get("skills") or "").split("|") if s.strip()]
    welfare = [w.strip() for w in str(raw.get("welfare") or "").split("|") if w.strip()]
    labels = [l.strip() for l in str(raw.get("job_labels") or "").split("|") if l.strip()]

    description = " | ".join(
        p for p in (
            str(raw.get("company_industry") or ""),
            str(raw.get("company_scale") or ""),
            str(raw.get("company_stage") or ""),
        ) if p
    )

    return {
        "platform": "zhipin",
        "platform_job_id": job_id[:128],
        "title": str(raw.get("title") or "")[:256],
        "company": str(raw.get("boss_name") or "未知公司")[:256],
        # 脚本保证薪资来自接口明文（默认禁用 DOM fallback）
        "salary": str(raw.get("salary") or "")[:64],
        "location": str(raw.get("location") or "")[:128],
        "experience": experience[:64],
        "education": education[:64],
        "tags": (labels + welfare)[:12],
        "description": description,
        "requirements": skills[:20],
        "url": link[:512],
        "salary_source": str(raw.get("salary_source") or "api"),
    }
