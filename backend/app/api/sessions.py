from fastapi import APIRouter, Depends, HTTPException, status

from app.core.auth_deps import get_current_user
from app.models.db_models import User
from app.models.schemas import AttachSessionRequest
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
        latest_resume = session_store.get_latest_resume(session["session_id"])
    if latest_resume is None:
        latest_resume = session_store.get_latest_resume_for_user(current_user.id)
    return {
        "session": session,
        "latest_resume": latest_resume,
    }
