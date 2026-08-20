"""职位爬虫调度器，运行间隔由环境变量按秒配置。"""
import asyncio
import datetime
import logging
import time
from typing import List

from app.core.database import SessionLocal, init_db
from app.core.config import settings
from app.models.db_models import Job, CrawlerStatus
from app.crawlers.zhaopin import ZhaopinCrawler
from app.crawlers.liepin import LiepinCrawler
from app.crawlers.external_boss import ExternalBossCrawler

logger = logging.getLogger("glint.scheduler")

if not 1 <= settings.CRAWLER_INTERVAL_SECONDS <= 24 * 60 * 60:
    raise RuntimeError("CRAWLER_INTERVAL_SECONDS 必须在 1 到 86400 之间")
CRAWL_INTERVAL_SECONDS = settings.CRAWLER_INTERVAL_SECONDS
JOB_RETENTION_SECONDS = 30 * 24 * 60 * 60
_crawl_lock = asyncio.Lock()


def _expire_and_cleanup() -> dict:
    """超过 30 天统一失效，并清理所有已失效职位。"""
    db = SessionLocal()
    try:
        now = datetime.datetime.now(datetime.timezone.utc)
        cutoff = now - datetime.timedelta(seconds=JOB_RETENTION_SECONDS)
        expired = db.query(Job).filter(Job.crawled_at < cutoff, Job.is_active == True).update(
            {Job.is_active: False}, synchronize_session=False
        )
        removed = db.query(Job).filter(Job.is_active == False).delete(synchronize_session=False)
        db.commit()
        return {"expired": expired, "removed": removed}
    except Exception as exc:
        db.rollback()
        logger.error("job_cleanup_failed", extra={"error": str(exc)})
        return {"expired": 0, "removed": 0}
    finally:
        db.close()


def _save_jobs(jobs: List[dict]) -> int:
    """将抓取结果写入 MySQL，按平台+职位ID 去重更新"""
    if not jobs:
        return 0

    deduped = {}
    for job in jobs:
        key = (job.get("platform", ""), job.get("platform_job_id", ""))
        if key[0] and key[1]:
            deduped[key] = job
    if not deduped:
        return 0

    db = SessionLocal()
    saved = 0
    try:
        now = datetime.datetime.now(datetime.timezone.utc)
        platforms = {platform for platform, _ in deduped}
        ids = {job_id for _, job_id in deduped}
        existing_rows = db.query(Job).filter(Job.platform.in_(platforms), Job.platform_job_id.in_(ids)).all()
        existing_map = {(row.platform, row.platform_job_id): row for row in existing_rows}
        for key, j in deduped.items():
            existing = existing_map.get(key)
            if existing:
                # 更新已有记录
                existing.title = j["title"]
                existing.company = j["company"]
                existing.salary = j["salary"]
                existing.location = j["location"]
                existing.experience = j["experience"]
                existing.education = j["education"]
                existing.tags = j["tags"]
                if j["description"]:
                    existing.description = j["description"]
                if j["requirements"]:
                    existing.requirements = j["requirements"]
                existing.url = j["url"]
                existing.is_active = True
                existing.crawled_at = now
                existing.updated_at = now
            else:
                # 新增
                db.add(Job(
                    platform=j["platform"],
                    platform_job_id=j["platform_job_id"],
                    title=j["title"],
                    company=j["company"],
                    salary=j["salary"],
                    location=j["location"],
                    experience=j["experience"],
                    education=j["education"],
                    tags=j["tags"],
                    description=j["description"],
                    requirements=j["requirements"],
                    url=j["url"],
                    is_active=True,
                    crawled_at=now,
                ))
            saved += 1

        db.commit()
        logger.info("jobs_saved", extra={"saved": saved})
    except Exception as e:
        db.rollback()
        logger.error("jobs_save_failed", extra={"error": str(e)})
        raise
    finally:
        db.close()
    return saved


def _update_status(platform: str, **fields) -> None:
    db = SessionLocal()
    try:
        row = db.query(CrawlerStatus).filter(CrawlerStatus.platform == platform).first()
        if row is None:
            row = CrawlerStatus(platform=platform)
            db.add(row)
        for key, value in fields.items():
            setattr(row, key, value)
        row.updated_at = datetime.datetime.now(datetime.timezone.utc)
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.error("crawler_status_save_failed", extra={"platform": platform, "error": str(exc)})
    finally:
        db.close()


def _new_crawlers():
    return [
        ("zhipin", ExternalBossCrawler()),
        ("zhaopin", ZhaopinCrawler()),
        ("liepin", LiepinCrawler()),
    ]


async def _crawl_platform(
    name: str,
    crawler,
    keywords: List[str] = None,
    cities: List[str] = None,
) -> tuple[str, int]:
    """抓取一个平台并记录运行状态。"""
    started = datetime.datetime.now(datetime.timezone.utc)
    started_monotonic = time.monotonic()
    _update_status(name, status="running", last_started_at=started, last_error="")
    try:
        logger.info("crawler_start", extra={"platform": name})
        jobs = await crawler.crawl(keywords=keywords, cities=cities)
        saved = _save_jobs(jobs)
        finished = datetime.datetime.now(datetime.timezone.utc)
        status_fields = {
            "status": "success" if jobs else "empty",
            "last_finished_at": finished,
            "last_job_count": len(jobs),
            "last_saved_count": saved,
            "last_duration_ms": round((time.monotonic() - started_monotonic) * 1000),
            "last_error": "" if jobs else "平台返回 0 条职位",
        }
        if jobs:
            status_fields["last_success_at"] = finished
        _update_status(name, **status_fields)
        logger.info("crawler_done", extra={"platform": name, "count": len(jobs)})
        return name, len(jobs)
    except Exception as exc:
        finished = datetime.datetime.now(datetime.timezone.utc)
        _update_status(
            name,
            status="failed",
            last_finished_at=finished,
            last_job_count=0,
            last_saved_count=0,
            last_duration_ms=round((time.monotonic() - started_monotonic) * 1000),
            last_error=str(exc)[:1000],
        )
        logger.error("crawler_failed", extra={"platform": name, "error": str(exc)})
        return name, 0
    finally:
        await crawler.close()


async def _crawl_platforms(keywords: List[str] = None, cities: List[str] = None) -> dict:
    pairs = await asyncio.gather(*(
        _crawl_platform(name, crawler, keywords=keywords, cities=cities)
        for name, crawler in _new_crawlers()
    ))
    return dict(pairs)


async def _crawl_all() -> dict:
    """并发运行全部平台爬虫。"""
    return await _crawl_platforms()


async def crawl_keyword(keyword: str, cities: List[str] = None) -> dict:
    """按用户当前搜索词抓取一次，供职位搜索接口在库为空时使用。"""
    keyword = (keyword or "").strip()
    if not keyword:
        return {"zhipin": 0, "zhaopin": 0, "liepin": 0}
    async with _crawl_lock:
        return await _crawl_platforms(keywords=[keyword], cities=cities)


async def _run_once():
    """执行一次全量抓取。"""
    logger.info("crawl_cycle_start")
    start = time.monotonic()
    async with _crawl_lock:
        results = await _crawl_all()
        cleanup = _expire_and_cleanup()
    logger.info(
        "crawl_cycle_done",
        extra={
            "results": results,
            "total": sum(results.values()),
            "cleanup": cleanup,
            "elapsed_seconds": round(time.monotonic() - start, 1),
        },
    )
    return results


async def run_scheduler():
    """启动定时调度器。"""
    init_db()
    logger.info("crawler_scheduler_started", extra={"interval_seconds": CRAWL_INTERVAL_SECONDS})
    while True:
        started = datetime.datetime.now(datetime.timezone.utc)
        try:
            await _run_once()
        except Exception as exc:
            logger.error("scheduler_cycle_error", extra={"error": str(exc)})
        next_run = started + datetime.timedelta(seconds=CRAWL_INTERVAL_SECONDS)
        delay = max(0, (next_run - datetime.datetime.now(datetime.timezone.utc)).total_seconds())
        logger.info("scheduler_next_run", extra={"next_at": next_run.isoformat()})
        await asyncio.sleep(delay)


if __name__ == "__main__":
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

    from app.core.logging_config import setup_logging
    setup_logging(level="INFO")

    asyncio.run(run_scheduler())
