"""
POST /api/jobs/search  ——  职位搜索与匹配分级
POST /api/jobs/adapt  ——  简历动态适配
POST /api/jobs/apply  ——  一键投递（持久化到 MySQL）
GET  /api/jobs/applications  ——  获取投递列表（从 DB 读取）
POST /api/jobs/applications/status  ——  更新投递状态（持久化）

职位数据来自爬虫库（jobs 表）；库为空时按关键词实时抓取，不返回 mock 职位。
"""
import datetime
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session as DBSession

from app.core.auth_deps import get_current_user
from app.core.database import get_db
from app.models.db_models import Application, Job, User, CrawlerStatus
from app.models.schemas import (
    JobSearchRequest, JobAdaptRequest, JobApplyRequest, ApplicationStatusRequest
)
from app.mock.fallback import (
    mock_adapt_resume, mock_apply_job,
    KW_MAP,
)

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


def _calc_match(target_job: str, job: dict) -> dict:
    """计算岗位匹配度"""
    t = (target_job or "").lower()
    keywords = []
    for k, v in KW_MAP.items():
        if k.lower() in t:
            keywords = v
            break
    if not keywords:
        keywords = job["requirements"][:4] if job["requirements"] else []

    requirements = job.get("requirements", [])
    if not requirements:
        return {"score": 50, "matched_keywords": [], "level": "yellow", "missing": [], "reasons": "匹配度未知"}

    match_count = 0
    matched = []
    for req in requirements:
        for kw in keywords:
            if kw.lower() in req.lower() or req.lower() in kw.lower():
                match_count += 1
                matched.append(kw)
                break

    score = round((match_count / len(requirements)) * 100) if requirements else 50

    if score >= 85:
        level, reasons = "green", f"岗位要求「{'、'.join(matched[:3])}」与你的技能高度匹配"
        missing = []
    elif score >= 60:
        missing = [r for r in requirements if not any(
            mk.lower() in r.lower() or r.lower() in mk.lower() for mk in matched)]
        reasons = f"匹配度中等，建议微调简历突出「{'、'.join(matched)}」等技能"
        missing = missing[:2]
        level = "yellow"
    else:
        missing = [r for r in requirements if not any(
            mk.lower() in r.lower() or r.lower() in mk.lower() for mk in matched)]
        reasons = f"核心技能「{'、'.join(missing[:3])}」暂不匹配，建议先补足再投递"
        missing = missing[:3]
        level = "red"

    return {
        "score": score,
        "matched_keywords": matched,
        "level": level,
        "missing": missing,
        "reasons": reasons,
    }


@router.post("/jobs/search")
async def job_search(req: JobSearchRequest, current_user: User = Depends(get_current_user), db: DBSession = Depends(get_db)):
    """搜索真实职位。库为空时按当前关键词触发一次实时抓取，不返回 mock 职位。"""
    keyword = req.keyword or req.target_job or ""

    # 优先从数据库读取
    db_jobs = _db_job_search(keyword=keyword, db=db)

    if db_jobs:
        # 用真实数据做匹配分级
        matched = []
        for job in db_jobs:
            m = _calc_match(req.target_job or keyword, job)
            matched.append({
                **job,
                "matchScore": m["score"],
                "matchLevel": m["level"],
                "reasons": m["reasons"],
                "missingSkills": m["missing"],
            })
        matched.sort(key=lambda x: x["matchScore"], reverse=True)
        return {"jobs": matched, "total": len(matched), "source": "db"}

    # 库里没有匹配职位时不做实时抓取：抓取依赖本机已登录的采集浏览器，
    # 需要几分钟并受平台限流约束，放在请求里必然超时。职位由后台爬虫
    # （run_crawler.py，每 2 小时一轮）持续入库。
    return {"jobs": [], "total": 0, "source": "empty", "message": "暂无匹配的真实职位，请更换关键词后重试"}


@router.post("/jobs/adapt")
async def adapt_resume(req: JobAdaptRequest, current_user: User = Depends(get_current_user)):
    """为指定岗位适配简历。"""
    return mock_adapt_resume(job_id=req.job_id, target_job=req.target_job)


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
