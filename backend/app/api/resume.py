"""
POST /api/resume/generate ——  基于对话生成简历 + 质量报告
GET  /api/resume/pdf       ——  导出简历为 A4 PDF
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response

from app.core.auth_deps import get_current_user
from app.core.config import settings
from app.core.input_sanitizer import sanitize_target_job
from app.models.db_models import User
from app.models.schemas import GenerateResumeRequest
from app.services import llm_service
from app.services.resume_service import generate_resume_from_session
from app.services.evaluation_service import evaluate_resume
from app.services.pdf_service import generate_pdf_bytes
from app.mock.fallback import mock_resume, mock_quality_report
from app.store.db_store import session_store

router = APIRouter()
logger = logging.getLogger("glint.api.resume")


@router.post("/resume/generate")
async def generate_resume(
    req: GenerateResumeRequest,
    current_user: User = Depends(get_current_user),
):
    user_id = current_user.id
    req.target_job = sanitize_target_job(req.target_job)
    session_store.get_or_create(req.session_id, req.target_job, user_id)

    def save_result(resume, quality_report, source="chat"):
        resume_id = session_store.save_resume(
            session_id=req.session_id,
            resume_json=resume,
            quality_report_json=quality_report,
            target_job=req.target_job,
            source=source,
            user_id=user_id,
        )
        logger.info("resume_saved", extra={
            "resume_id": resume_id,
            "session_id": req.session_id,
            "user_id": user_id or "anonymous",
            "source": source,
        })
        return resume_id

    if not settings.llm_available:
        resume = mock_resume(req.target_job)
        quality_report = mock_quality_report()
        resume_id = save_result(resume, quality_report, source="mock")
        return {
            "resume": resume,
            "quality_report": quality_report,
            "saved_resume_id": resume_id,
            "fallback": True,
            "fallback_reason": "LLM 服务未配置，当前展示的是示例内容",
        }

    try:
        with llm_service.usage_context(
            user_id=user_id,
            session_id=req.session_id,
            endpoint="/api/resume/generate",
            source="resume_generate",
        ):
            resume = await generate_resume_from_session(req.session_id, req.target_job)
            # 没有经历就没有可写的简历。此时绝不能返回示例内容:
            # 用户会拿到一份姓名和项目都不属于自己的简历,却标着"基于真实经历重塑"。
            # 宁可明确告知需要继续补充,也不伪造。
            if not resume.get("experiences"):
                logger.warning("resume_empty_experiences_reject", extra={
                    "session_id": req.session_id,
                    "user_id": user_id,
                })
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="还没聊到你的具体经历，无法生成简历。请回到对话继续描述你的项目、实习或活动经历。",
                )
            quality_report = await evaluate_resume(resume, req.target_job)
        resume_id = save_result(resume, quality_report)
        return {"resume": resume, "quality_report": quality_report, "saved_resume_id": resume_id}
    except HTTPException:
        raise
    except llm_service.LLMQuotaExceeded as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc))
    except Exception:
        logger.exception("resume_generate_fallback", extra={
            "session_id": req.session_id,
            "user_id": user_id,
        })
        resume = mock_resume(req.target_job)
        quality_report = mock_quality_report()
        resume_id = save_result(resume, quality_report, source="mock")
        return {
            "resume": resume,
            "quality_report": quality_report,
            "saved_resume_id": resume_id,
            "fallback": True,
            "fallback_reason": "当前 AI 服务繁忙，展示的是示例内容",
        }


@router.get("/resumes")
def list_resumes(
    limit: int = Query(30, ge=1, le=100),
    current_user: User = Depends(get_current_user),
):
    return {"resumes": session_store.get_resumes_for_user(current_user.id, limit=limit)}


@router.get("/resumes/{resume_id}")
def get_resume(
    resume_id: int,
    current_user: User = Depends(get_current_user),
):
    resume = session_store.get_resume_for_user(resume_id, current_user.id)
    if resume is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="简历不存在")
    return {"resume": resume}


@router.delete("/resumes/{resume_id}")
def delete_resume(
    resume_id: int,
    current_user: User = Depends(get_current_user),
):
    deleted = session_store.delete_resume_for_user(resume_id, current_user.id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="简历不存在")
    return {"ok": True}


@router.get("/resume/pdf")
def export_resume_pdf(
    resume_id: int = Query(..., description="简历 ID"),
    current_user: User = Depends(get_current_user),
):
    """导出简历为 A4 PDF 文件"""
    resume_record = session_store.get_resume_for_user(resume_id, current_user.id)
    if resume_record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="简历不存在")

    resume_data = resume_record.get("resume") or {}
    if not resume_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="简历数据为空")

    try:
        pdf_bytes = generate_pdf_bytes(resume_data)
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    fullname = (resume_data.get("basic") or {}).get("fullname") or "简历"
    filename = f"{fullname}_识光简历.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(pdf_bytes)),
        },
    )
