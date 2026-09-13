from fastapi import APIRouter, Depends, HTTPException, status

from app.core.auth_deps import get_current_user
from app.models.db_models import User
from app.models.schemas import AttachSessionRequest, SessionLayoutRequest
from app.services import resume_sections as sections
from app.store.db_store import session_store

router = APIRouter()


@router.post("/sessions/attach")
def attach_session(
    req: AttachSessionRequest,
    current_user: User = Depends(get_current_user),
):
    try:
        session = session_store.attach_to_user(
            session_id=req.session_id,
            user_id=current_user.id,
            target_job=req.target_job,
        )
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="该会话已属于其他用户",
        )
    return {"session": session}


@router.get("/sessions/latest")
def latest_session(current_user: User = Depends(get_current_user)):
    session = session_store.get_latest_for_user(current_user.id)
    latest_resume = None
    if session:
        latest_resume = session_store.get_latest_resume(session["session_id"], current_user.id)
    if latest_resume is None:
        latest_resume = session_store.get_latest_resume_for_user(current_user.id)
    return {
        "session": session,
        "latest_resume": latest_resume,
    }


@router.get("/sessions/sections")
def list_sections():
    """简历板块定义(前端板块面板与排序控件的元数据来源)。"""
    return {
        "sections": sections.SECTIONS,
        "default_order": sections.DEFAULT_SECTION_ORDER,
        "hub_stage": sections.HUB_STAGE,
        "ready_stage": sections.READY_STAGE,
    }


@router.post("/sessions/layout")
def update_session_layout(
    req: SessionLayoutRequest,
    current_user: User = Depends(get_current_user),
):
    """对话进行中调整简历正文板块顺序;生成简历时沿用该顺序。"""
    session = session_store.get(req.session_id, current_user.id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")
    progress = sections.normalize_progress(session.get("progress"))
    progress["order"] = sections.normalize_section_order(req.section_order)
    session_store.update_progress(req.session_id, progress, current_user.id)
    return {"progress": progress}
