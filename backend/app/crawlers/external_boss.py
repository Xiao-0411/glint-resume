"""Adapter for the vendored BOSS scraper project.

The scraper is deliberately executed as a subprocess. This keeps
its dependencies and runtime isolated from FastAPI and gives the caller a
stable JSON boundary for normalized jobs.
"""
import asyncio
import json
import os
import sys
import tempfile
import uuid
from pathlib import Path
from typing import List
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from app.crawlers.base import BaseCrawler, JOB_KEYWORDS, select_cities
from app.crawlers.cdp_browser import fetch_boss_detail

VENDORED_DIR = Path(__file__).resolve().parents[2] / "vendor" / "boss-zhipin-scraper"
VENDORED_SCRIPT = VENDORED_DIR / "scripts" / "boss_cdp_raw.py"


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} 必须是整数") from exc
    if not minimum <= value <= maximum:
        raise RuntimeError(f"{name} 必须在 {minimum} 到 {maximum} 之间")
    return value


def _command_for(keyword: str, output_path: str, city: str = "") -> list[str]:
    if not VENDORED_SCRIPT.is_file():
        raise RuntimeError(f"项目内 BOSS 爬虫不存在: {VENDORED_SCRIPT}")
    city = city.strip() or os.getenv("BOSS_SCRAPER_CITY", "上海").strip() or "上海"
    pages = _env_int("BOSS_SCRAPER_PAGES", 1, 1, 10)
    cdp_port = _env_int("BOSS_SCRAPER_CDP_PORT", 9222, 1, 65535)
    return [
        sys.executable,
        str(VENDORED_SCRIPT),
        "--keyword", keyword,
        "--city", city,
        "--pages", str(pages),
        "--cdp-port", str(cdp_port),
        "--no-detail",
        "--output", output_path,
    ]


def _decode_jobs(stdout: str) -> list[dict]:
    payload = json.loads(stdout)
    if isinstance(payload, dict):
        payload = payload.get("jobs", payload.get("data", []))
    if not isinstance(payload, list):
        raise RuntimeError("外部 BOSS 爬虫输出必须是 JSON 数组或 {jobs: []}")
    return [item for item in payload if isinstance(item, dict)]


def _as_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.replace("|", ",").split(",") if item.strip()]
    return []


def _detail_url(raw: dict) -> str:
    url = str(raw.get("url") or raw.get("job_link") or "").strip()
    if not url:
        return ""
    parsed = urlparse(url)
    params = parse_qsl(parsed.query, keep_blank_values=True)
    existing = {key for key, _ in params}
    for query_key, raw_key in (("securityId", "security_id"), ("lid", "lid")):
        value = str(raw.get(raw_key) or "").strip()
        if value and query_key not in existing:
            params.append((query_key, value))
    return urlunparse(parsed._replace(query=urlencode(params)))


def _normalize_external_job(raw: dict) -> dict:
    """Map the vendored scraper schema to the application's Job schema."""
    tag_values = _as_list(raw.get("tags"))
    education_levels = {"初中及以下", "中专", "中技", "高中", "大专", "本科", "硕士", "博士", "学历不限"}
    education = next((value for value in tag_values if value in education_levels), "")
    experience = next((value for value in tag_values if "经验" in value or "年" in value or value in {"应届生", "在校生"}), "")
    job_id = raw.get("job_id") or raw.get("id") or raw.get("encrypt_job_id") or ""
    return {
        **raw,
        "job_id": job_id,
        "company": raw.get("company", raw.get("boss_name", "")),
        "url": _detail_url(raw),
        "experience": raw.get("experience", experience),
        "education": raw.get("education", education),
        "tags": tag_values + _as_list(raw.get("job_labels")),
        "requirements": _as_list(raw.get("requirements")) + _as_list(raw.get("skills")),
        # 列表抓取使用 --no-detail，卡片字段不能当作完整岗位描述。
        "description": "",
    }


class ExternalBossCrawler(BaseCrawler):
    platform = "zhipin"
    base_url = "https://www.zhipin.com"

    async def _run(self, keyword: str, city: str = "") -> list[dict]:
        output_path = os.path.join(tempfile.gettempdir(), f"glint-boss-{uuid.uuid4().hex}.json")
        try:
            process = await asyncio.create_subprocess_exec(
                *_command_for(keyword, output_path, city),
                cwd=str(VENDORED_DIR),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            timeout = _env_int("BOSS_SCRAPER_TIMEOUT_SECONDS", 90, 10, 600)
            try:
                _, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
            except asyncio.TimeoutError:
                process.kill()
                await process.communicate()
                raise RuntimeError(f"BOSS 爬虫超过 {timeout} 秒未完成")
            if process.returncode != 0:
                detail = stderr.decode("utf-8", errors="replace").strip()[-1000:]
                raise RuntimeError(f"BOSS 爬虫退出码 {process.returncode}: {detail}")
            try:
                with open(output_path, encoding="utf-8") as handle:
                    return _decode_jobs(handle.read())
            except FileNotFoundError:
                return []
            except (OSError, json.JSONDecodeError, RuntimeError) as exc:
                raise RuntimeError(f"BOSS 爬虫输出无效: {exc}") from exc
        finally:
            try:
                os.remove(output_path)
            except FileNotFoundError:
                pass

    async def crawl(self, keywords: List[str] = None, cities: List[str] = None) -> List[dict]:
        jobs: list[dict] = []
        seen: set[str] = set()
        selected_keywords = keywords or JOB_KEYWORDS
        selected_cities = select_cities(cities)
        if keywords is None:
            max_keywords = _env_int("BOSS_SCRAPER_MAX_KEYWORDS", 5, 1, len(JOB_KEYWORDS))
            selected_keywords = selected_keywords[:max_keywords]
        for city in selected_cities:
            for keyword in selected_keywords:
                for raw in await self._run(keyword, city):
                    job = self.normalize_job(_normalize_external_job(raw))
                    if not job["platform_job_id"]:
                        continue
                    key = job["platform_job_id"]
                    if key not in seen:
                        seen.add(key)
                        jobs.append(job)
        return jobs

    async def fetch_detail(self, job: dict) -> dict:
        url = str(job.get("url") or "").strip()
        if not url:
            return {}
        port = _env_int("BOSS_SCRAPER_CDP_PORT", 9222, 1, 65535)
        return await asyncio.to_thread(fetch_boss_detail, url, port)
