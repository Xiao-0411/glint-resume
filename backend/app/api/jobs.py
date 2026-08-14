"""
POST /api/jobs/search  ——  职位搜索与匹配分级
POST /api/jobs/adapt  ——  简历动态适配
POST /api/jobs/apply  ——  一键投递（持久化到 MySQL）
GET  /api/jobs/applications  ——  获取投递列表（从 DB 读取）
POST /api/jobs/applications/status  ——  更新投递状态（持久化）

职位数据来自爬虫库（jobs 表）；库为空时按关键词实时抓取，不返回 mock 职位。

匹配度基于用户**真实简历**与 JD 的技能比对，技能权重取自真实 JD 语料的
市场频率（见 services/job_match.py 与 services/jd_corpus.py）。
"""
import datetime
import json
import uuid
import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import or_
from sqlalchemy.orm import Session as DBSession

from app.core.auth_deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.models.db_models import Application, Job, User, CrawlerStatus
from app.models.schemas import (
    JobSearchRequest, JobAdaptRequest, JobApplyRequest, ApplicationStatusRequest
)
from app.mock.fallback import mock_apply_job
from app.services import llm_service
from app.services.evaluation_service import evaluate_resume
from app.services.jd_corpus import build_profile
from app.services.job_adapt import AdaptError, adapt_resume_to_job
from app.services.job_match import rank_jobs
from app.store.db_store import session_store
from app.crawlers.scheduler import crawl_keyword

logger = logging.getLogger("glint.jobs")

router = APIRouter()


@router.get("/jobs/crawler-status")
async def crawler_status(current_user: User = Depends(get_current_user), db: DBSession = Depends(get_db)):
    """返回三个招聘渠道最近一次抓取状态。"""
    rows = {row.platform: row for row in db.query(CrawlerStatus).all()}
    platforms = {"zhipin": "BOSS直聘", "zhaopin": "智联招聘", "liepin": "猎聘"}
    data = []
    for platform, label in platforms.items():
        row = rows.get(platform)
        data.append({
            "platform": platform,
            "label": label,
            "status": row.status if row else "never",
            "lastStartedAt": row.last_started_at.isoformat() if row and row.last_started_at else "",
            "lastFinishedAt": row.last_finished_at.isoformat() if row and row.last_finished_at else "",
            "lastSuccessAt": row.last_success_at.isoformat() if row and row.last_success_at else "",
            "lastJobCount": row.last_job_count if row else 0,
            "lastSavedCount": row.last_saved_count if row else 0,
            "lastDurationMs": row.last_duration_ms if row else 0,
            "lastError": row.last_error if row else "",
        })
    return {"platforms": data}

STATUS_LABEL_MAP = {
    "applied": "已投递",
    "screened": "简历通过筛选",
    "interviewing": "面试邀约",
    "offered": "已获Offer",
    "rejected": "未通过筛选",
    "withdrawn": "已撤回",
}


def _db_job_search(keyword: str = "", db: DBSession = None, limit: int = 60) -> list:
    """从 MySQL jobs 表搜索职位"""
    if db is None:
        return []

    query = db.query(Job).filter(Job.is_active == True)

    if keyword:
        kw = f"%{keyword}%"
        query = query.filter(
            or_(
                Job.title.like(kw),
                Job.company.like(kw),
                Job.location.like(kw),
                Job.description.like(kw),
            )
        )

    rows = query.order_by(Job.crawled_at.desc(), Job.id.desc()).limit(limit).all()

    results = []
    for row in rows:
        results.append({
            "id": f"job_db_{row.id}",
            "title": row.title,
            "company": row.company,
            "salary": row.salary or "薪资面议",
            "location": row.location or "全国",
            "tags": row.tags or [],
            "description": row.description or "",
            "requirements": row.requirements or [],
            "platform": row.platform,
            "url": row.url or "",
            "crawledAt": row.crawled_at.isoformat() if row.crawled_at else "",
        })
    return results


def _load_user_resume(user_id: str) -> dict:
    """取用户最新一份简历用于匹配。取不到就返回空 dict —— 由匹配层给出
    "尚未生成简历"的明确结论，而不是编一个分数出来。"""
    try:
        latest = session_store.get_latest_resume_for_user(user_id)
    except Exception as exc:
        logger.warning("load_resume_for_match_failed", extra={"user_id": user_id, "error": str(exc)})
        return {}
    return (latest or {}).get("resume") or {}


@router.post("/jobs/search")
async def job_search(req: JobSearchRequest, current_user: User = Depends(get_current_user), db: DBSession = Depends(get_db)):
    """搜索真实职位。库为空时按当前关键词触发一次实时抓取，不返回 mock 职位。

    匹配度用用户最新简历与 JD 比对得出，因此同一岗位下不同用户分数不同。
    """
    keyword = req.keyword or req.target_job or ""
    resume = _load_user_resume(current_user.id)
    target_job = req.target_job or keyword

    db_jobs = _db_job_search(keyword=keyword, db=db)
    source = "db"

    if not db_jobs and keyword:
        try:
            await asyncio.wait_for(crawl_keyword(keyword), timeout=35)
        except asyncio.TimeoutError:
            return {"jobs": [], "total": 0, "source": "live_unavailable", "message": "实时职位抓取超时，请稍后重试"}
        except Exception:
            return {"jobs": [], "total": 0, "source": "live_unavailable", "message": "实时职位暂时不可用，请稍后重试"}

        # 抓取器使用独立 DB 会话写入；结束本请求旧的读事务，避免 MySQL
        # REPEATABLE READ 快照看不到刚提交的职位。
        db.rollback()
        db_jobs = _db_job_search(keyword=keyword, db=db)
        source = "live"

    if not db_jobs:
        return {"jobs": [], "total": 0, "source": "empty", "message": "暂无匹配的真实职位，请更换关键词后重试"}

    # build_profile 会扫 JD 语料并跑大量正则,rank_jobs 要对每个职位做技能抽取。
    # 两者都是同步的 CPU + DB 工作,直接在 async 函数里跑会阻塞事件循环
    # (语料缓存未命中时实测约 200ms),放到线程池执行。
    profile = await run_in_threadpool(build_profile, db, target_job)
    matched = await run_in_threadpool(rank_jobs, resume, db_jobs, profile)
    return {
        "jobs": matched,
        "total": len(matched),
        "source": source,
        # 让前端能如实说明匹配依据，而不是笼统写"与你的简历匹配"
        "matchBasis": {
            "hasResume": bool(resume),
            "profileSource": profile.source,
            "sampleSize": profile.sample_size,
            "targetJob": target_job,
        },
    }


def _load_db_job(job_id: str, db: DBSession) -> dict:
    """按 job_id 取真实职位。取不到返回空 dict。"""
    if not job_id.startswith("job_db_"):
        return {}
    try:
        row_id = int(job_id.replace("job_db_", ""))
    except ValueError:
        return {}
    row = db.query(Job).filter(Job.id == row_id, Job.is_active == True).first()
    if row is None:
        return {}
    return {
        "id": job_id,
        "title": row.title,
        "company": row.company,
        "description": row.description or "",
        "requirements": row.requirements or [],
        "tags": row.tags or [],
    }


@router.post("/jobs/adapt")
async def adapt_resume(
    req: JobAdaptRequest,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """针对指定岗位适配用户的真实简历。

    读 resumes 表里用户最近一份简历 + jobs 表里的真实 JD,由 LLM 做定向改写
    (只调措辞、不造经历,见 services/job_adapt),前后分数用真实评分算出。
    """
    if not settings.llm_available:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI 服务未配置，暂时无法进行岗位适配",
        )

    resume = _load_user_resume(current_user.id)
    job = _load_db_job(req.job_id, db)
    target_job = job.get("title") or req.target_job

    try:
        profile = await run_in_threadpool(build_profile, db, target_job)
        with llm_service.usage_context(
            user_id=current_user.id,
            endpoint="/api/jobs/adapt",
            source="job_adapt",
        ):
            return await adapt_resume_to_job(
                resume=resume,
                job=job,
                profile=profile,
                score_fn=evaluate_resume,
            )
    except AdaptError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except llm_service.LLMQuotaExceeded as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc))
    except (llm_service.LLMError, json.JSONDecodeError):
        # 改写本身失败时不返回编造内容,让用户知道可以重试
        logger.warning("job_adapt_llm_failed", extra={"job_id": req.job_id})
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI 适配暂时不可用，请稍后重试",
        )


@router.post("/jobs/apply")
async def apply_job(
    req: JobApplyRequest,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """一键投递 —— 持久化到 applications 表。"""
    # 尝试从 DB 查找职位信息
    job_title = ""
    company = ""
    if req.job_id.startswith("job_db_"):
        try:
            db_job_id = int(req.job_id.replace("job_db_", ""))
        except ValueError:
            db_job_id = None
        if db_job_id is not None:
            job_row = db.query(Job).filter(Job.id == db_job_id).first()
            if job_row:
                job_title = job_row.title
                company = job_row.company

    if not job_title:
        # fallback mock
        mock_result = mock_apply_job(job_id=req.job_id, resume_version=req.resume_version)
        job_title = mock_result.get("jobTitle", "")
        company = mock_result.get("company", "")

    now = datetime.datetime.now(datetime.timezone.utc)
    app_id = f"app_{uuid.uuid4().hex[:12]}"

    application = Application(
        id=app_id,
        user_id=current_user.id,
        job_id=req.job_id,
        job_title=job_title or "未知职位",
        company=company or "未知公司",
        resume_version=req.resume_version or "original",
        status="applied",
        status_label="已投递",
        status_history=[{"status": "applied", "at": now.isoformat(), "label": "简历已投递"}],
        applied_at=now,
    )
    db.add(application)
    db.commit()
    db.refresh(application)

    return {
        "applicationId": application.id,
        "jobId": application.job_id,
        "jobTitle": application.job_title,
        "company": application.company,
        "resumeVersion": application.resume_version,
        "appliedAt": application.applied_at.isoformat() if application.applied_at else "",
        "status": application.status,
        "statusLabel": application.status_label,
        "statusHistory": application.status_history or [],
    }


@router.get("/jobs/applications")
async def get_applications(
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """获取当前用户所有投递记录和统计（从 DB 读取）。"""
    rows = (
        db.query(Application)
        .filter(Application.user_id == current_user.id)
        .order_by(Application.applied_at.desc(), Application.id.desc())
        .all()
    )

    if not rows:
        return {"applications": [], "stats": {
            "total": 0, "screened": 0, "interviewing": 0, "offered": 0, "rejected": 0,
        }}

    applications = []
    for row in rows:
        applications.append({
            "id": row.id,
            "jobId": row.job_id,
            "jobTitle": row.job_title,
            "company": row.company,
            "resumeVersion": row.resume_version,
            "appliedAt": row.applied_at.isoformat() if row.applied_at else "",
            "status": row.status,
            "statusLabel": row.status_label,
            "statusHistory": row.status_history or [],
        })

    total = len(applications)
    stats = {
        "total": total,
        "screened": sum(1 for a in applications if a["status"] in ("screened", "interviewing", "offered", "rejected")),
        "interviewing": sum(1 for a in applications if a["status"] in ("interviewing", "offered")),
        "offered": sum(1 for a in applications if a["status"] == "offered"),
        "rejected": sum(1 for a in applications if a["status"] == "rejected"),
    }

    return {"applications": applications, "stats": stats}


@router.post("/jobs/applications/status")
async def update_application_status(
    req: ApplicationStatusRequest,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """更新投递状态 —— 持久化到 DB。"""
    application = (
        db.query(Application)
        .filter(Application.id == req.application_id, Application.user_id == current_user.id)
        .first()
    )
    if application is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="投递记录不存在")

    now = datetime.datetime.now(datetime.timezone.utc)
    label = STATUS_LABEL_MAP.get(req.status, req.status)

    history = list(application.status_history or [])
    history.append({"status": req.status, "at": now.isoformat(), "label": label})

    application.status = req.status
    application.status_label = label
    application.status_history = history
    application.updated_at = now
    db.commit()

    return {
        "applicationId": application.id,
        "status": application.status,
        "statusLabel": application.status_label,
        "updatedAt": now.isoformat(),
    }
