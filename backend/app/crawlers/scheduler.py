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
from app.models.db_models import Job
from app.crawlers.zhipin import ZhipinCrawler
from app.crawlers.zhaopin import ZhaopinCrawler
from app.crawlers.liepin import LiepinCrawler

logger = logging.getLogger("glint.scheduler")

CRAWL_INTERVAL_SECONDS = 2 * 60 * 60  # 2 小时


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


async def _crawl_all() -> dict:
    """运行全部平台爬虫"""
    results = {}
    crawlers = [
        ("zhipin", ZhipinCrawler()),
        ("zhaopin", ZhaopinCrawler()),
        ("liepin", LiepinCrawler()),
    ]

    for name, crawler in crawlers:
        try:
            logger.info("crawler_start", extra={"platform": name})
            jobs = await crawler.crawl()
            results[name] = len(jobs)
            _save_jobs(jobs)
            logger.info("crawler_done", extra={"platform": name, "count": len(jobs)})
        except Exception as e:
            logger.error("crawler_failed", extra={"platform": name, "error": str(e)})
            results[name] = 0
        finally:
            await crawler.close()

    return results


async def _run_once():
    """执行一次全量抓取"""
    logger.info("crawl_cycle_start")
    start = time.time()
    results = await _crawl_all()
    elapsed = time.time() - start
    total = sum(results.values())
    logger.info(
        "crawl_cycle_done",
        extra={"results": results, "total": total, "elapsed_seconds": round(elapsed, 1)},
    )
    return results


async def run_scheduler():
    """启动定时调度器：每 2 小时执行一次"""
    init_db()
    logger.info(
        "scheduler_started",
        extra={"interval_hours": CRAWL_INTERVAL_SECONDS / 3600},
    )

    while True:
        try:
            await _run_once()
        except Exception as e:
            logger.error("scheduler_cycle_error", extra={"error": str(e)})

        next_run = datetime.datetime.now() + datetime.timedelta(seconds=CRAWL_INTERVAL_SECONDS)
        logger.info(
            "scheduler_next_run",
            extra={"next_at": next_run.isoformat()},
        )
        await asyncio.sleep(CRAWL_INTERVAL_SECONDS)


if __name__ == "__main__":
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

    from app.core.logging_config import setup_logging
    setup_logging(level="INFO")

    asyncio.run(run_scheduler())