"""
POST /api/jobs/search  ——  职位搜索与匹配分级
POST /api/jobs/adapt  ——  简历动态适配
POST /api/jobs/apply  ——  一键投递（持久化到 MySQL）
GET  /api/jobs/applications  ——  获取投递列表（从 DB 读取）
POST /api/jobs/applications/status  ——  更新投递状态（持久化）

注:求职加速为 demo 演示模块,职位数据来自 mock(无真实职位数据源),
与 LLM 是否可用无关。投递记录已持久化到 applications 表。
"""
import datetime
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session as DBSession

from app.core.auth_deps import get_current_user
from app.core.database import get_db
from app.models.db_models import Application, User
from app.models.schemas import (
    JobSearchRequest, JobAdaptRequest, JobApplyRequest, ApplicationStatusRequest
)
from app.mock.fallback import (
    mock_job_search, mock_adapt_resume, mock_apply_job,
    mock_get_applications, mock_update_application_status
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


@router.post("/jobs/search")
async def job_search(req: JobSearchRequest, current_user: User = Depends(get_current_user)):
    """搜索职位并进行匹配分级。输出: { jobs: [...], total: int }"""
    return mock_job_search(keyword=req.keyword, target_job=req.target_job)


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
    # 从 mock 数据中查找职位信息
    mock_result = mock_apply_job(job_id=req.job_id, resume_version=req.resume_version)
    now = datetime.datetime.now(datetime.timezone.utc)
    app_id = f"app_{uuid.uuid4().hex[:12]}"

    application = Application(
        id=app_id,
        user_id=current_user.id,
        job_id=req.job_id,
        job_title=mock_result.get("jobTitle", ""),
        company=mock_result.get("company", ""),
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
