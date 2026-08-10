"""
POST /api/jobs/search  ——  职位搜索与匹配分级
POST /api/jobs/adapt  ——  简历动态适配
POST /api/jobs/apply  ——  一键投递（持久化到 MySQL）
GET  /api/jobs/applications  ——  获取投递列表（从 DB 读取）
POST /api/jobs/applications/status  ——  更新投递状态（持久化）

职位数据优先从爬虫库（jobs 表）读取，库为空时 fallback 到 mock 数据。
"""
import datetime
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session as DBSession

from app.core.auth_deps import get_current_user
from app.core.database import get_db
from app.models.db_models import Application, Job, User
from app.models.schemas import (
    JobSearchRequest, JobAdaptRequest, JobApplyRequest, ApplicationStatusRequest
)
from app.mock.fallback import (
    mock_job_search, mock_adapt_resume, mock_apply_job,
    KW_MAP,
)

router = APIRouter()

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
            # 真实职位才有的字段 —— 前端据此展示"查看原始职位"入口
            "experience": row.experience or "",
            "education": row.education or "",
            "url": row.url or "",
            "platform": row.platform or "",
            "isReal": True,
        })
    return results


def _calc_match(target_job: str, job: dict) -> dict:
    """计算岗位匹配度。

    真实职位的 requirements 来自 JD 正文提取，可能为空（详情页配额没轮到它）。
    这种情况下不能编一个分数出来 —— 标成 unknown，让前端明确显示"待评估"，
    而不是给个 50 分的黄灯误导用户去投递。
    """
    requirements = job.get("requirements") or []
    if not requirements:
        return {
            "score": None,
            "matched_keywords": [],
            "level": "unknown",
            "missing": [],
            "reasons": "该职位描述尚未同步，暂无法评估匹配度，可点击查看原始职位了解详情",
        }

    t = (target_job or "").lower()
    keywords = []
    for k, v in KW_MAP.items():
        if k.lower() in t:
            keywords = v
            break

    # 没命中预设岗位画像时，用职位自身要求当基准会得出 100% 的虚高分数
    # （自己跟自己比），所以退回按目标岗位名做字面匹配。
    if not keywords:
        keywords = [w for w in re.split(r"[\s/、,，]+", target_job or "") if len(w) >= 2]

    if not keywords:
        return {
            "score": None,
            "matched_keywords": [],
            "level": "unknown",
            "missing": [],
            "reasons": "填写目标岗位后即可查看匹配度分析",
        }

    matched = []
    for req in requirements:
        for kw in keywords:
            if kw.lower() in req.lower() or req.lower() in kw.lower():
                if kw not in matched:
                    matched.append(kw)
                break

    # 以「目标岗位要求的技能被这个职位覆盖了多少」为准
    score = round((len(matched) / len(keywords)) * 100)
    missing = [r for r in requirements if not any(
        mk.lower() in r.lower() or r.lower() in mk.lower() for mk in matched)]

    if score >= 70:
        level = "green"
        reasons = f"岗位要求「{'、'.join(matched[:3])}」与你的技能高度匹配"
        missing = []
    elif score >= 40:
        level = "yellow"
        reasons = f"匹配度中等，建议微调简历突出「{'、'.join(matched[:3])}」等技能"
        missing = missing[:2]
    else:
        level = "red"
        hint = '、'.join(missing[:3]) if missing else '、'.join(keywords[:3])
        reasons = f"核心技能「{hint}」暂不匹配，建议先补足再投递"
        missing = missing[:3]

    return {
        "score": score,
        "matched_keywords": matched,
        "level": level,
        "missing": missing,
        "reasons": reasons,
    }


@router.post("/jobs/search")
async def job_search(req: JobSearchRequest, current_user: User = Depends(get_current_user), db: DBSession = Depends(get_db)):
    """搜索职位并进行匹配分级。优先从爬虫库读取，库空时回退 mock 并明确告知用户。"""
    keyword = req.keyword or req.target_job or ""

    # 优先从数据库读取真实职位
    db_jobs = _db_job_search(keyword=keyword, db=db)

    # 关键词没搜到，但库里有真实职位 —— 退回展示最新职位，别拿假数据糊弄
    if not db_jobs and keyword:
        db_jobs = _db_job_search(keyword="", db=db)

    if db_jobs:
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
        # 能算出分的排前面，待评估的沉底；同分按抓取时间（列表已按 crawled_at 倒序）
        matched.sort(key=lambda x: (x["matchScore"] is not None, x["matchScore"] or 0), reverse=True)
        return {"jobs": matched, "total": len(matched), "source": "db"}

    # 数据库为空 —— 回退示例数据，但必须让用户知道这不是真实岗位
    result = mock_job_search(keyword=keyword, target_job=req.target_job)
    result["source"] = "mock"
    result["isDemo"] = True
    result["notice"] = "职位库正在同步中，当前展示的是示例职位，仅供体验匹配功能，请勿据此投递。"
    for job in result.get("jobs", []):
        job["isReal"] = False
        job["url"] = ""
    return result


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
