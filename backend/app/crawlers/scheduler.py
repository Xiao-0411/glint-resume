"""
职位爬虫调度器 —— 每 2 小时自动运行一次
可作为独立脚本运行，也可集成到 FastAPI 启动时
"""
import asyncio
import datetime
import logging
import time
from typing import List

from sqlalchemy import and_

from app.core.database import SessionLocal, init_db
from app.models.db_models import Job, CrawlerStatus
from app.crawlers.base import JOB_KEYWORDS
from app.crawlers.zhipin import ZhipinCrawler
from app.crawlers.zhaopin import ZhaopinCrawler
from app.crawlers.liepin import LiepinCrawler
from app.crawlers.browser_session import BrowserSessionCollector

logger = logging.getLogger("glint.scheduler")

CRAWL_INTERVAL_SECONDS = 2 * 60 * 60  # 2 小时
JOB_RETENTION_SECONDS = 30 * 24 * 60 * 60


def _expire_and_cleanup() -> dict:
    """超过 30 天统一失效，并清理所有已失效职位。"""
    db = SessionLocal()
    try:
        now = datetime.datetime.now(datetime.timezone.utc)
        cutoff = now - datetime.timedelta(seconds=JOB_RETENTION_SECONDS)
        expired = db.query(Job).filter(Job.created_at < cutoff, Job.is_active == True).update(
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

    db = SessionLocal()
    saved = 0
    try:
        now = datetime.datetime.now(datetime.timezone.utc)
        for j in jobs:
            existing = (
                db.query(Job)
                .filter(
                    and_(
                        Job.platform == j["platform"],
                        Job.platform_job_id == j["platform_job_id"],
                    )
                )
                .first()
            )
            if existing:
                # 更新已有记录
                existing.title = j["title"]
                existing.company = j["company"]
                existing.salary = j["salary"]
                existing.location = j["location"]
                existing.experience = j["experience"]
                existing.education = j["education"]
                existing.tags = j["tags"]
                existing.description = j["description"]
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


async def _crawl_all() -> dict:
    """运行全部平台爬虫"""
    results = {}
    crawlers = [
        ("zhipin", ZhipinCrawler()),
        ("zhaopin", ZhaopinCrawler()),
        ("liepin", LiepinCrawler()),
    ]

    for name, crawler in crawlers:
        started = datetime.datetime.now(datetime.timezone.utc)
        started_monotonic = time.monotonic()
        _update_status(name, status="running", last_started_at=started, last_error="")
        try:
            logger.info("crawler_start", extra={"platform": name})
            jobs = await crawler.crawl()
            results[name] = len(jobs)
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
            results[name] = 0
        finally:
            await crawler.close()

    return results


async def crawl_keyword(keyword: str) -> dict:
    """按用户当前搜索词抓取一次，供职位搜索接口在库为空时使用。"""
    keyword = (keyword or "").strip()
    if not keyword:
        return {"zhipin": 0, "zhaopin": 0, "liepin": 0}

    results = {}
    crawlers = [
        ("zhipin", ZhipinCrawler()),
        ("zhaopin", ZhaopinCrawler()),
        ("liepin", LiepinCrawler()),
    ]
    for name, crawler in crawlers:
        started = datetime.datetime.now(datetime.timezone.utc)
        started_monotonic = time.monotonic()
        _update_status(name, status="running", last_started_at=started, last_error="")
        try:
            jobs = await crawler.crawl(keywords=[keyword])
            results[name] = len(jobs)
            saved = _save_jobs(jobs)
            finished = datetime.datetime.now(datetime.timezone.utc)
            status_fields = {
                "status": "success" if jobs else "empty", "last_finished_at": finished,
                "last_job_count": len(jobs), "last_saved_count": saved,
                "last_duration_ms": round((time.monotonic() - started_monotonic) * 1000),
                "last_error": "" if jobs else "平台返回 0 条职位",
            }
            if jobs:
                status_fields["last_success_at"] = finished
            _update_status(name, **status_fields)
        except Exception as exc:
            finished = datetime.datetime.now(datetime.timezone.utc)
            _update_status(name, status="failed", last_finished_at=finished, last_job_count=0,
                           last_saved_count=0, last_duration_ms=round((time.monotonic() - started_monotonic) * 1000),
                           last_error=str(exc)[:1000])
            logger.warning("crawler_keyword_failed", extra={"platform": name, "keyword": keyword, "error": str(exc)})
            results[name] = 0
        finally:
            await crawler.close()
    return results


async def _run_once():
    """执行一次全量抓取"""
    logger.info("crawl_cycle_start")
    start = time.time()
    results = await _crawl_all()
    cleanup = _expire_and_cleanup()
    elapsed = time.time() - start
    total = sum(results.values())
    logger.info(
        "crawl_cycle_done",
        extra={"results": results, "total": total, "cleanup": cleanup, "elapsed_seconds": round(elapsed, 1)},
    )
    return results


async def run_scheduler():
    """启动定时调度器：每 2 小时执行一次"""
    init_db()
    browser_collector = BrowserSessionCollector()
    try:
        await browser_collector.start_and_wait_for_login()
        logger.info("scheduler_started", extra={"interval_hours": CRAWL_INTERVAL_SECONDS / 3600})

        while True:
            try:
                # 浏览器以正常用户方式打开三个平台，读取页面可见职位。
                results = {}
                started = time.monotonic()
                captured = await browser_collector.crawl_all(JOB_KEYWORDS)
                for platform, jobs in captured.items():
                    saved = _save_jobs(jobs)
                    results[platform] = len(jobs)
                    finished = datetime.datetime.now(datetime.timezone.utc)
                    error = browser_collector.errors.get(platform, "")
                    status_fields = {
                        "status": "failed" if error else ("success" if jobs else "empty"),
                        "last_started_at": finished, "last_finished_at": finished,
                        "last_job_count": len(jobs), "last_saved_count": saved,
                        "last_duration_ms": round((time.monotonic() - started) * 1000),
                        "last_error": error or ("页面未显示职位，可能需要登录或被平台风控拦截" if not jobs else ""),
                    }
                    if jobs and not error:
                        status_fields["last_success_at"] = finished
                    _update_status(platform, **status_fields)
                cleanup = _expire_and_cleanup()
                logger.info("browser_crawl_cycle_done", extra={"results": results, "cleanup": cleanup})
            except Exception as exc:
                logger.error("scheduler_cycle_error", extra={"error": str(exc)})

            next_run = datetime.datetime.now() + datetime.timedelta(seconds=CRAWL_INTERVAL_SECONDS)
            logger.info("scheduler_next_run", extra={"next_at": next_run.isoformat()})
            await asyncio.sleep(CRAWL_INTERVAL_SECONDS)
    finally:
        await browser_collector.close()


if __name__ == "__main__":
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

    from app.core.logging_config import setup_logging
    setup_logging(level="INFO")

    asyncio.run(run_scheduler())
