"""职位爬虫调度器 —— 每 2 小时自动运行一次。

三个平台统一走 cdp_collector 的原生 CDP 引擎，可作为独立脚本运行
（run_crawler.py），也可由一键启动脚本拉起。
"""
import asyncio
import datetime
import functools
import logging
import time
from typing import List

from sqlalchemy import and_
from sqlalchemy.exc import IntegrityError

from app.core.database import SessionLocal, init_db
from app.models.db_models import Job, CrawlerStatus
from app.crawlers.api_capture import JOB_KEYWORDS
from app.crawlers.cdp_collector import PLATFORM_LABELS, UnifiedCDPCollector

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
            # 每条一个 savepoint：撞上唯一索引时只回滚这一条，不丢整批
            try:
                with db.begin_nested():
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
                        # 更新已有记录。薪资只在新值非空时覆盖，避免一次降级抓取
                        # （DOM 字体反爬拿不到薪资）把库里已有的明文薪资清空。
                        existing.title = j["title"]
                        existing.company = j["company"]
                        if j.get("salary"):
                            existing.salary = j["salary"]
                        existing.location = j["location"] or existing.location
                        existing.experience = j["experience"] or existing.experience
                        existing.education = j["education"] or existing.education
                        existing.tags = j["tags"] or existing.tags
                        existing.description = j["description"] or existing.description
                        existing.requirements = j["requirements"] or existing.requirements
                        existing.url = j["url"] or existing.url
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
            except IntegrityError:
                # 并发抓取时另一个进程刚插入了同一条，跳过即可
                logger.debug(
                    "job_duplicate_skipped",
                    extra={"platform": j.get("platform"), "job_id": j.get("platform_job_id")},
                )

        db.commit()
        logger.info("jobs_saved", extra={"saved": saved})
    except Exception as e:
        db.rollback()
        logger.error("jobs_save_failed", extra={"error": str(e)})
        return 0
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


# 这些函数都是同步 SQLAlchemy 调用。从 async 上下文（尤其是 FastAPI 请求）
# 里直接调用会阻塞事件循环，所以统一走线程池。
async def _save_jobs_async(jobs: List[dict]) -> int:
    return await asyncio.to_thread(_save_jobs, jobs)


async def _update_status_async(platform: str, **fields) -> None:
    await asyncio.to_thread(functools.partial(_update_status, platform, **fields))


async def _expire_and_cleanup_async() -> dict:
    return await asyncio.to_thread(_expire_and_cleanup)


async def _persist_platform(platform: str, jobs: list, error: str, is_blocked: bool,
                            started_monotonic: float) -> dict:
    """写入职位并更新该平台的抓取状态。"""
    saved = await _save_jobs_async(jobs)
    finished = datetime.datetime.now(datetime.timezone.utc)
    if is_blocked:
        status = "blocked"
    elif error:
        status = "failed"
    elif jobs:
        status = "success"
    else:
        status = "empty"
    status_fields = {
        "status": status,
        "last_finished_at": finished,
        "last_job_count": len(jobs), "last_saved_count": saved,
        "last_duration_ms": round((time.monotonic() - started_monotonic) * 1000),
        "last_error": error or ("接口返回 0 条职位" if not jobs else ""),
    }
    if jobs and not error:
        status_fields["last_success_at"] = finished
    await _update_status_async(platform, **status_fields)
    return {"fetched": len(jobs), "saved": saved}


async def run_scheduler():
    """启动定时调度器：每 2 小时执行一次。

    三个平台统一走 cdp_collector（vendor 的原生 CDP 引擎）：自动拉起专用
    Chrome、自动等登录、之后全自动循环，不需要人工再做别的操作。
    """
    init_db()
    collector = UnifiedCDPCollector()
    try:
        await collector.start_and_wait_for_login()
        logger.info("scheduler_started", extra={"interval_hours": CRAWL_INTERVAL_SECONDS / 3600})

        while True:
            cycle_started = time.monotonic()
            try:
                results = {}
                active = [p for p in collector.platforms if not collector.blocked.get(p)]
                for platform in active:
                    await _update_status_async(
                        platform,
                        status="running",
                        last_started_at=datetime.datetime.now(datetime.timezone.utc),
                        last_error="",
                    )

                captured = await collector.crawl_all(JOB_KEYWORDS)
                for platform, jobs in captured.items():
                    results[platform] = await _persist_platform(
                        platform, jobs,
                        collector.errors.get(platform, ""),
                        collector.blocked.get(platform, False),
                        cycle_started,
                    )

                cleanup = await _expire_and_cleanup_async()
                logger.info(
                    "crawl_cycle_done",
                    extra={
                        "results": results,
                        "cleanup": cleanup,
                        "elapsed_seconds": round(time.monotonic() - cycle_started, 1),
                    },
                )
                total_saved = sum(r["saved"] for r in results.values())
                summary = "，".join(
                    f"{PLATFORM_LABELS.get(p, p)} {r['fetched']} 条" for p, r in results.items()
                )
                print(f"本轮完成：{summary}；入库 {total_saved} 条。", flush=True)
            except Exception as exc:
                logger.exception("scheduler_cycle_error", extra={"error": str(exc)})

            next_run = datetime.datetime.now() + datetime.timedelta(seconds=CRAWL_INTERVAL_SECONDS)
            logger.info("scheduler_next_run", extra={"next_at": next_run.isoformat()})
            await asyncio.sleep(CRAWL_INTERVAL_SECONDS)
    finally:
        await collector.close()
