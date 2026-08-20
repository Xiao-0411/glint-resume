"""职位爬虫调度器，运行间隔由环境变量按秒配置。"""
import asyncio
import datetime
import os
import random
import time
from typing import List

from app.core.database import SessionLocal, init_db
from app.core.config import settings
from app.models.db_models import Job, CrawlerStatus
from app.crawlers.cursor import cursor_snapshot
from app.crawlers.zhaopin import ZhaopinCrawler
from app.crawlers.liepin import LiepinCrawler
from app.crawlers.external_boss import ExternalBossCrawler
from app.core.logging_config import get_logger

logger = get_logger("glint.scheduler")

if not 1 <= settings.CRAWLER_INTERVAL_SECONDS <= 24 * 60 * 60:
    raise RuntimeError("CRAWLER_INTERVAL_SECONDS 必须在 1 到 86400 之间")
CRAWL_INTERVAL_SECONDS = settings.CRAWLER_INTERVAL_SECONDS
# 单轮耗时经常超过配置间隔（实测猎聘一轮约 6 分钟）。此时仍强制静默一小段，
# 否则调度器会不间断地连续请求，显著抬高触发风控的概率。
MIN_IDLE_SECONDS = 30
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


def _classify_before_save(jobs: List[dict]) -> List[dict]:
    """入库前同步分类。

    未配置分类接口、或调用失败时，原样返回岗位：宁可 category 留空
    等后续补分类，也不因为分类失败丢弃已经抓到的数据。
    """
    if not jobs:
        return jobs
    try:
        from app.services import job_classifier
    except ImportError as exc:  # noqa: BLE001
        logger.warning("classifier_import_failed", extra={"error": str(exc)})
        return jobs

    if not job_classifier.is_configured():
        logger.info("classifier_skipped", extra={"reason": "未配置 JOB_CLASSIFIER_*", "count": len(jobs)})
        return jobs

    try:
        batch_size = int(os.getenv("JOB_CLASSIFIER_BATCH_SIZE", "20"))
    except ValueError:
        batch_size = 20

    results = job_classifier.classify_all(jobs, batch_size=max(1, batch_size))
    classified = [
        job_classifier.apply_classification(job, result)
        for job, result in zip(jobs, results)
    ]
    filled = sum(1 for r in results if r)
    logger.info("jobs_classified", extra={"total": len(jobs), "classified": filled})
    return classified


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

    # 分类在写库之前完成，保证库里不出现未分类的中间态。
    keys = list(deduped.keys())
    classified = _classify_before_save([deduped[key] for key in keys])
    deduped = dict(zip(keys, classified))

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
                # 分类失败时保留原值，避免把已分类记录冲成空。
                if j.get("category"):
                    existing.category = j["category"]
                if j.get("job_level"):
                    existing.job_level = j["job_level"]
                if j.get("industry"):
                    existing.industry = j["industry"]
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
                    category=j.get("category", ""),
                    job_level=j.get("job_level", ""),
                    industry=j.get("industry", ""),
                    detail_status="done" if j.get("description") else "pending",
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


def _crawler_for_platform(platform: str):
    """按平台名新建爬虫实例；未知平台返回 None。"""
    factories = {
        "zhipin": ExternalBossCrawler,
        "zhaopin": ZhaopinCrawler,
        "liepin": LiepinCrawler,
    }
    factory = factories.get(platform)
    return factory() if factory else None


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


async def _backfill_details() -> dict:
    """后台逐条补齐岗位 JD。

    JD 只入库供匹配度使用，前端不展示，因此这里刻意做成低速旁路：
    - 详情页是平台反爬盯得最紧的入口，必须逐条串行并保持人类节奏；
    - 连续失败达到阈值立刻收手，避免风控期间持续送死；
    - 单条失败标记 failed 并跳过，不影响主抓取流程。
    """
    if os.getenv("JD_BACKFILL_ENABLED", "true").lower() != "true":
        return {"skipped": "disabled"}

    def _int_env(name: str, default: int) -> int:
        try:
            return int(os.getenv(name, str(default)))
        except ValueError:
            return default

    batch = max(1, _int_env("JD_BACKFILL_BATCH", 15))
    min_delay = max(1, _int_env("JD_BACKFILL_MIN_DELAY", 12))
    max_delay = max(min_delay, _int_env("JD_BACKFILL_MAX_DELAY", 25))
    fail_threshold = max(1, _int_env("JD_BACKFILL_FAIL_THRESHOLD", 3))

    db = SessionLocal()
    try:
        # 优先补最新抓到的岗位：用户更可能搜到它们。
        rows = (
            db.query(Job)
            .filter(Job.is_active == True, Job.detail_status == "pending", Job.url != "")
            .order_by(Job.crawled_at.desc())
            .limit(batch)
            .all()
        )
        targets = [
            {"id": row.id, "platform": row.platform, "url": row.url, "title": row.title}
            for row in rows
        ]
    finally:
        db.close()

    if not targets:
        return {"pending": 0, "done": 0, "failed": 0}

    crawlers: dict = {}
    done = failed = 0
    consecutive_failures = 0
    risk_signal = ""

    try:
        for index, target in enumerate(targets):
            platform = target["platform"]
            if platform not in crawlers:
                crawler = _crawler_for_platform(platform)
                if crawler is None:
                    _mark_detail_status(target["id"], "unsupported")
                    continue
                crawlers[platform] = crawler

            try:
                detail = await asyncio.wait_for(
                    crawlers[platform].fetch_detail(target),
                    timeout=settings.CRAWLER_DETAIL_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                detail, error = {}, "详情抓取超时"
            except Exception as exc:  # noqa: BLE001
                detail, error = {}, str(exc)
            else:
                error = ""

            description = str((detail or {}).get("description") or "").strip()
            if description:
                _mark_detail_status(
                    target["id"], "done",
                    description=description,
                    requirements=(detail or {}).get("requirements") or [],
                )
                done += 1
                consecutive_failures = 0
            else:
                _mark_detail_status(target["id"], "failed")
                failed += 1
                consecutive_failures += 1
                # 登录失效/风控是全局性故障，继续抓只会加剧封禁。
                if "登录状态已失效" in error or "风控" in error:
                    risk_signal = error
                    logger.error("jd_backfill_blocked", extra={"error": error[:200]})
                    break
                if consecutive_failures >= fail_threshold:
                    risk_signal = f"连续 {consecutive_failures} 条失败，疑似被限流：{error[:120]}"
                    logger.warning("jd_backfill_aborted", extra={"error": risk_signal})
                    break

            if index < len(targets) - 1:
                await asyncio.sleep(random.uniform(min_delay, max_delay))
    finally:
        for crawler in crawlers.values():
            try:
                await crawler.close()
            except Exception:  # noqa: BLE001
                pass

    if risk_signal:
        _update_status("jd_backfill", status="failed", last_error=risk_signal[:1000])
    else:
        _update_status(
            "jd_backfill",
            status="success" if done else "empty",
            last_job_count=len(targets),
            last_saved_count=done,
            last_error="" if done else "本轮未补到任何 JD",
        )

    logger.info("jd_backfill_done", extra={"attempted": len(targets), "done": done, "failed": failed})
    return {"attempted": len(targets), "done": done, "failed": failed}


def _mark_detail_status(job_id: int, status: str, **fields) -> None:
    db = SessionLocal()
    try:
        row = db.query(Job).filter(Job.id == job_id).first()
        if row is None:
            return
        row.detail_status = status
        description = fields.get("description")
        if description:
            row.description = description
        requirements = fields.get("requirements")
        if requirements:
            # AI 分类产出的技能与平台原始要求合并去重。
            existing = [str(r).strip() for r in (row.requirements or []) if str(r).strip()]
            seen = {item.lower() for item in existing}
            row.requirements = existing + [
                str(r).strip() for r in requirements
                if str(r).strip() and str(r).strip().lower() not in seen
            ]
        row.updated_at = datetime.datetime.now(datetime.timezone.utc)
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.error("detail_status_update_failed", extra={"job_id": job_id, "error": str(exc)})
    finally:
        db.close()


async def _run_once():
    """执行一次全量抓取。"""
    logger.info("crawl_cycle_start")
    start = time.monotonic()
    async with _crawl_lock:
        results = await _crawl_all()
        cleanup = _expire_and_cleanup()
        # JD 补全放在锁内串行执行，避免与列表抓取同时占用浏览器。
        backfill = await _backfill_details()
    logger.info(
        "crawl_cycle_done",
        extra={
            "results": results,
            "total": sum(results.values()),
            "cleanup": cleanup,
            "backfill": backfill,
            "elapsed_seconds": round(time.monotonic() - start, 1),
        },
    )
    return results


async def run_scheduler():
    """启动定时调度器。

    全量覆盖靠游标滚动完成，而不是靠单轮抓完：每轮只处理一个
    「城市切片 × 关键词切片」，跑完立刻进入下一轮。因此间隔只是两轮之间的
    喘息时间，真实周期由单轮耗时决定；若上一轮已超过间隔，则至少静默
    MIN_IDLE_SECONDS 再继续，避免连续冲击目标站点触发风控。
    """
    init_db()
    logger.info("crawler_scheduler_started", extra={"interval_seconds": CRAWL_INTERVAL_SECONDS})
    while True:
        started = datetime.datetime.now(datetime.timezone.utc)
        try:
            await _run_once()
        except Exception as exc:
            logger.error("scheduler_cycle_error", extra={"error": str(exc)})
        next_run = started + datetime.timedelta(seconds=CRAWL_INTERVAL_SECONDS)
        remaining = (next_run - datetime.datetime.now(datetime.timezone.utc)).total_seconds()
        delay = max(MIN_IDLE_SECONDS, remaining)
        logger.info(
            "scheduler_next_run",
            extra={
                "next_at": (
                    datetime.datetime.now(datetime.timezone.utc)
                    + datetime.timedelta(seconds=delay)
                ).isoformat(),
                "overran": remaining < 0,
                "cursor": cursor_snapshot(),
            },
        )
        await asyncio.sleep(delay)


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

    from app.core.logging_config import setup_logging
    setup_logging(level="INFO")

    asyncio.run(run_scheduler())
