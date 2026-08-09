"""
POST /api/resume/evaluate-text  ——  PDF 解析文本 → 简历 + 质量报告
POST /api/resume/evaluate       ——  对已有简历对象直接重评(用户编辑后重新评定)
"""
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.auth_deps import get_current_user
from app.core.config import settings
from app.core.input_sanitizer import sanitize_target_job
from app.models.db_models import User
from app.models.schemas import EvaluateTextRequest, EvaluateResumeRequest
from app.services import llm_service
from app.services.resume_service import evaluate_uploaded_text
from app.services.evaluation_service import evaluate_resume
from app.mock.fallback import mock_resume, mock_quality_report
from app.store.db_store import session_store

router = APIRouter()
logger = logging.getLogger("glint.api.evaluation")


@router.post("/resume/evaluate-text")
async def evaluate_text(
    req: EvaluateTextRequest,
    current_user: User = Depends(get_current_user),
):
    user_id = current_user.id
    req.target_job = sanitize_target_job(req.target_job)
    if req.session_id:
        session_store.get_or_create(req.session_id, req.target_job, user_id)

    if not settings.llm_available:
        resume = mock_resume(req.target_job)
        quality_report = mock_quality_report(
            from_upload=True, source_file=req.file_name
        )
        resume_id = _save_resume_result(
            req=req,
            resume=resume,
            quality_report=quality_report,
            source="upload_mock",
            current_user=current_user,
        )
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
            endpoint="/api/resume/evaluate-text",
            source="upload",
        ):
            result = await evaluate_uploaded_text(req.text, req.file_name)
        resume_id = _save_resume_result(
            req=req,
            resume=result.get("resume") or {},
            quality_report=result.get("quality_report") or {},
            source="upload",
            current_user=current_user,
        )
        return {
            **result,
            "saved_resume_id": resume_id,
        }
    except llm_service.LLMQuotaExceeded as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc))
    except Exception:
        logger.exception("evaluate_text_fallback", extra={
            "session_id": req.session_id,
            "user_id": user_id,
            "file_name": req.file_name,
        })
        resume = mock_resume(req.target_job)
        quality_report = mock_quality_report(
            from_upload=True, source_file=req.file_name
        )
        resume_id = _save_resume_result(
            req=req,
            resume=resume,
            quality_report=quality_report,
            source="upload_mock",
            current_user=current_user,
        )
        return {
            "resume": resume,
            "quality_report": quality_report,
            "saved_resume_id": resume_id,
            "fallback": True,
            "fallback_reason": "当前 AI 服务繁忙，展示的是示例内容",
        }


@router.post("/resume/evaluate")
async def evaluate_resume_endpoint(
    req: EvaluateResumeRequest,
    current_user: User = Depends(get_current_user),
):
    """直接对传入的简历对象做五维评分(保留其 exp_id),用于用户编辑后的重评。
    不重新生成简历,因此 evidence/target_exp_id 始终与当前简历对齐。"""
    user_id = current_user.id
    req.target_job = sanitize_target_job(req.target_job)
    if req.session_id:
        session_store.get_or_create(req.session_id, req.target_job, user_id)

    if not settings.llm_available:
        quality_report = mock_quality_report()
        resume_id = _save_resume_result(
            req=req,
            resume=req.resume,
            quality_report=quality_report,
            source="edit_mock",
            current_user=current_user,
        )
        return {
            "quality_report": quality_report,
            "saved_resume_id": resume_id,
            "fallback": True,
            "fallback_reason": "LLM 服务未配置，当前展示的是示例内容",
        }
    try:
        with llm_service.usage_context(
            user_id=user_id,
            session_id=req.session_id,
            endpoint="/api/resume/evaluate",
            source="edit",
        ):
            report = await evaluate_resume(req.resume, req.target_job)
        resume_id = _save_resume_result(
            req=req,
            resume=req.resume,
            quality_report=report,
            source="edit",
            current_user=current_user,
        )
        return {"quality_report": report, "saved_resume_id": resume_id}
    except llm_service.LLMQuotaExceeded as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc))
    except Exception:
        logger.exception("evaluate_resume_fallback", extra={
            "session_id": req.session_id,
            "user_id": user_id,
        })
        quality_report = mock_quality_report()
        resume_id = _save_resume_result(
            req=req,
            resume=req.resume,
            quality_report=quality_report,
            source="edit_mock",
            current_user=current_user,
        )
        return {
            "quality_report": quality_report,
            "saved_resume_id": resume_id,
            "fallback": True,
            "fallback_reason": "当前 AI 服务繁忙，展示的是示例内容",
        }


def _save_resume_result(
    req,
    resume: dict,
    quality_report: dict,
    source: str,
    current_user: User,
):
    user_id = current_user.id
    session_id = req.session_id or f"{source}_{uuid.uuid4().hex}"
    target_job = req.target_job or resume.get("basic", {}).get("target_job", "")
    resume_id = session_store.save_resume(
        session_id=session_id,
        resume_json=resume,
        quality_report_json=quality_report,
        target_job=target_job,
        source=source,
        user_id=user_id,
    )
    logger.info("resume_saved", extra={
        "resume_id": resume_id,
        "session_id": session_id,
        "user_id": user_id or "anonymous",
        "source": source,
    })
    return resume_id
