"""
职位爬虫调度器 —— 每 2 小时自动运行一次
可作为独立脚本运行，也可集成到 FastAPI 启动时

数据源现状（2026-08 实测）：
- 猎聘：搜索接口可用且稳定，是当前唯一真实数据来源
- Boss直聘：接口返回 code=37 风控；浏览器方案被检测 headless，有头模式弹验证码
- 智联招聘：接口返回 200 但 results 恒为空
后两者已停用，详见 zhipin.py / zhaopin.py 顶部说明。

JD 正文补全策略：
猎聘详情页有 IP 级配额，一轮只能抓十几条就会被重定向到营销页。所以列表数据
先全量入库（不受限），JD 单独做增量补全 —— 每轮挑一批还没有 JD 的职位去补，
撞到配额就停，下一轮继续。跑几轮之后覆盖率自然爬上来。
"""
import asyncio
import datetime
import logging
import time
from typing import List

from sqlalchemy import and_, or_

from app.core.database import SessionLocal, init_db
from app.models.db_models import Job
from app.crawlers.liepin import LiepinCrawler

logger = logging.getLogger("glint.scheduler")

CRAWL_INTERVAL_SECONDS = 2 * 60 * 60  # 2 小时

# 每轮抓取覆盖的城市（猎聘城市码见 liepin.LIEPIN_CITIES）
CRAWL_CITIES = ["全国", "北京", "上海", "深圳", "杭州", "广州"]
# 每个「关键词 × 城市」抓几页，每页约 42 条
CRAWL_PAGES = 1
# 每轮补 JD 的目标条数上限
DETAIL_BATCH = 60
# 职位超过这个天数没再被抓到，视为已下架
STALE_DAYS = 7


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
                existing.title = j["title"]
                existing.company = j["company"]
                existing.salary = j["salary"]
                existing.location = j["location"]
                existing.experience = j["experience"]
                existing.education = j["education"]
                existing.tags = j["tags"]
                # 列表抓取不带 JD，别把已经补好的正文覆盖成空
                if j["description"]:
                    existing.description = j["description"]
                if j["requirements"]:
                    existing.requirements = j["requirements"]
                existing.url = j["url"]
                existing.is_active = True
                existing.crawled_at = now
                existing.updated_at = now
            else:
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


async def _fill_missing_details(limit: int = DETAIL_BATCH) -> dict:
    """给库里还没有 JD 正文的职位补详情。

    顺带处理已下架职位：详情页还在但没有 JD 正文的，直接置为失效，
    否则它们会永远排在待补队列前面，每轮都白抓一次。
    """
    db = SessionLocal()
    try:
        rows = (
            db.query(Job)
            .filter(
                Job.platform == "liepin",
                Job.is_active == True,  # noqa: E712
                or_(Job.description == "", Job.description.is_(None)),
            )
            .order_by(Job.crawled_at.desc())
            .limit(limit)
            .all()
        )
        pending = [{"id": r.id, "url": r.url, "tags": list(r.tags or [])} for r in rows]
    finally:
        db.close()

    if not pending:
        logger.info("detail_fill_skip", extra={"reason": "no_pending"})
        return {"pending": 0, "filled": 0, "expired": 0}

    crawler = LiepinCrawler()
    try:
        await crawler.fill_details(pending, stop_on_block=True)
    finally:
        await crawler.close()

    filled = 0
    expired = 0
    db = SessionLocal()
    try:
        now = datetime.datetime.now(datetime.timezone.utc)
        for item in pending:
            row = db.query(Job).filter(Job.id == item["id"]).first()
            if row is None:
                continue

            if item.get("expired"):
                row.is_active = False
                row.updated_at = now
                expired += 1
                continue

            if not item.get("description"):
                continue

            row.description = item["description"]
            row.requirements = item.get("requirements") or []
            if item.get("tags"):
                row.tags = item["tags"]
            row.updated_at = now
            filled += 1
        db.commit()
        logger.info(
            "detail_fill_done",
            extra={"pending": len(pending), "filled": filled, "expired": expired},
        )
    except Exception as e:
        db.rollback()
        logger.error("detail_fill_save_failed", extra={"error": str(e)})
    finally:
        db.close()

    return {"pending": len(pending), "filled": filled, "expired": expired}


def _deactivate_stale(days: int = STALE_DAYS) -> int:
    """把长期没再抓到的职位标记为失效，避免前端展示过期岗位"""
    db = SessionLocal()
    try:
        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
        stale = (
            db.query(Job)
            .filter(Job.is_active == True, Job.crawled_at < cutoff)  # noqa: E712
            .all()
        )
        for row in stale:
            row.is_active = False
        db.commit()
        if stale:
            logger.info("jobs_deactivated", extra={"count": len(stale)})
        return len(stale)
    except Exception as e:
        db.rollback()
        logger.error("jobs_deactivate_failed", extra={"error": str(e)})
        return 0
    finally:
        db.close()


async def _crawl_all() -> dict:
    """运行全部可用平台的爬虫"""
    results = {}
    crawler = LiepinCrawler()
    try:
        logger.info("crawler_start", extra={"platform": "liepin"})
        # 列表抓取不补详情 —— 详情走 _fill_missing_details 的增量通道
        jobs = await crawler.crawl(
            cities=CRAWL_CITIES, pages=CRAWL_PAGES, with_detail=False
        )
        _save_jobs(jobs)
        results["liepin"] = len(jobs)
        logger.info("crawler_done", extra={"platform": "liepin", "count": len(jobs)})
    except Exception as e:
        logger.error("crawler_failed", extra={"platform": "liepin", "error": str(e)})
        results["liepin"] = 0
    finally:
        await crawler.close()

    return results


async def _run_once():
    """执行一次全量抓取 + 增量补 JD + 清理过期"""
    logger.info("crawl_cycle_start")
    start = time.time()

    results = await _crawl_all()
    detail_stats = await _fill_missing_details()
    _deactivate_stale()

    elapsed = time.time() - start
    total = sum(results.values())
    logger.info(
        "crawl_cycle_done",
        extra={
            "results": results,
            "total": total,
            "detail_filled": detail_stats.get("filled", 0),
            "elapsed_seconds": round(elapsed, 1),
        },
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
