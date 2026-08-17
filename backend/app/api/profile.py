"""
个人中心 —— 资料维护、头像上传与数据概览。

登录/注册留在 auth.py，这里只处理"已登录用户管理自己"的场景。
"""
import datetime
import logging
import secrets
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from sqlalchemy import func
from sqlalchemy.orm import Session as DBSession

from app.api.auth import _validate_password_policy
from app.core.auth_deps import get_current_user
from app.core.database import get_db
from app.core.security import hash_password, verify_password
from app.models.db_models import Application, Resume, User
from app.models.schemas import (
    AuthUser,
    PasswordChangeRequest,
    ProfileStats,
    ProfileUpdateRequest,
)

logger = logging.getLogger("glint.profile")

router = APIRouter()

# ====== 头像上传约束 ======
# backend/uploads/avatars —— 与 main.py 的 StaticFiles 挂载路径保持一致
AVATAR_DIR = Path(__file__).resolve().parents[2] / "uploads" / "avatars"
AVATAR_URL_PREFIX = "/uploads/avatars"
AVATAR_MAX_BYTES = 2 * 1024 * 1024  # 2MB
# multipart 的 boundary、文件名等额外开销，按 Content-Length 预判时留出余量
_MULTIPART_OVERHEAD = 4096
# 只认这几种，且以真实文件头为准 —— 扩展名和 content-type 都是客户端说了算，不可信
AVATAR_MAGIC = {
    b"\xff\xd8\xff": ".jpg",
    b"\x89PNG\r\n\x1a\n": ".png",
    b"GIF87a": ".gif",
    b"GIF89a": ".gif",
}


def _detect_image_ext(head: bytes) -> str | None:
    """按文件头判断图片类型，返回扩展名；不认识则返回 None。"""
    for magic, ext in AVATAR_MAGIC.items():
        if head.startswith(magic):
            return ext
    # webp: RIFF....WEBP
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return ".webp"
    return None


@router.get("/profile", response_model=AuthUser)
def get_profile(current_user: User = Depends(get_current_user)):
    return _to_auth_user(current_user)


@router.patch("/profile", response_model=AuthUser)
def update_profile(
    req: ProfileUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """更新昵称 / 头像。字段为 None 表示不改。"""
    user = db.query(User).filter(User.id == current_user.id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

    if req.display_name is not None:
        name = req.display_name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="昵称不能为空")
        if len(name) > 32:
            raise HTTPException(status_code=400, detail="昵称最长 32 个字符")
        user.display_name = name

    if req.avatar is not None:
        avatar = req.avatar.strip()
        # 只接受本站上传产出、且属于自己的文件名。否则用户可以把 avatar 指向
        # 别人的头像，下次换头像时 _remove_old_avatar 就会顺手删掉别人的文件。
        if avatar and not _is_own_avatar(avatar, user.id):
            raise HTTPException(status_code=400, detail="头像地址无效，请通过上传接口设置")
        user.avatar = avatar

    db.commit()
    db.refresh(user)
    return _to_auth_user(user)


@router.post("/profile/avatar", response_model=AuthUser)
async def upload_avatar(
    request: Request,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """上传头像图片，落盘后把访问路径写回用户记录。"""
    # 先看 Content-Length 挡掉超大请求。等到读 body 再判断就晚了 ——
    # 那时 multipart 已经把整个请求收完并落到临时文件。
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > AVATAR_MAX_BYTES + _MULTIPART_OVERHEAD:
        raise HTTPException(status_code=413, detail="头像不能超过 2MB")

    raw = await file.read(AVATAR_MAX_BYTES + 1)
    if not raw:
        raise HTTPException(status_code=400, detail="文件为空")
    if len(raw) > AVATAR_MAX_BYTES:
        raise HTTPException(status_code=413, detail="头像不能超过 2MB")

    ext = _detect_image_ext(raw[:16])
    if ext is None:
        raise HTTPException(status_code=400, detail="仅支持 JPG / PNG / GIF / WebP 图片")

    user = db.query(User).filter(User.id == current_user.id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

    AVATAR_DIR.mkdir(parents=True, exist_ok=True)
    # 文件名带随机串:换头像后 URL 必变，绕开浏览器/CDN 对旧图的缓存
    filename = f"{user.id}_{secrets.token_hex(6)}{ext}"
    (AVATAR_DIR / filename).write_bytes(raw)

    old_avatar = user.avatar or ""
    user.avatar = f"{AVATAR_URL_PREFIX}/{filename}"
    db.commit()
    db.refresh(user)

    _remove_old_avatar(old_avatar, keep=filename)
    return _to_auth_user(user)


@router.post("/profile/password")
def change_password(
    req: PasswordChangeRequest,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    user = db.query(User).filter(User.id == current_user.id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    if not user.password_hash or not verify_password(req.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="当前密码不正确")
    if req.current_password == req.new_password:
        raise HTTPException(status_code=400, detail="新密码不能与当前密码相同")
    _validate_password_policy(req.new_password)

    user.password_hash = hash_password(req.new_password)
    db.commit()
    return {"message": "密码修改成功"}


@router.get("/profile/stats", response_model=ProfileStats)
def get_profile_stats(
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """个人中心顶部的数据概览。"""
    resume_agg = (
        db.query(
            func.count(Resume.id),
            func.max(Resume.total_score),
            func.avg(Resume.total_score),
            func.max(Resume.created_at),
        )
        .filter(Resume.user_id == current_user.id)
        .one()
    )
    resume_count, best_score, average_score, last_resume_at = resume_agg

    application_count = (
        db.query(func.count(Application.id))
        .filter(Application.user_id == current_user.id)
        .scalar()
    ) or 0
    interview_count = (
        db.query(func.count(Application.id))
        .filter(
            Application.user_id == current_user.id,
            Application.status.in_(("interviewing", "offered")),
        )
        .scalar()
    ) or 0

    return ProfileStats(
        resume_count=resume_count or 0,
        best_score=int(best_score) if best_score is not None else None,
        average_score=round(float(average_score), 1) if average_score is not None else None,
        application_count=application_count,
        interview_count=interview_count,
        last_resume_at=_iso(last_resume_at),
    )


def _is_own_avatar(avatar: str, user_id: str) -> bool:
    """avatar 是否是本站上传、且文件名归属该用户的头像。"""
    if not avatar.startswith(AVATAR_URL_PREFIX + "/"):
        return False
    name = Path(avatar).name
    # 上传时命名为 {user_id}_{随机}{ext}
    return bool(name) and name.startswith(f"{user_id}_") and (AVATAR_DIR / name).exists()


def _remove_old_avatar(old_avatar: str, keep: str):
    """换头像后清掉旧文件，失败不影响主流程。"""
    if not old_avatar or not old_avatar.startswith(AVATAR_URL_PREFIX + "/"):
        return
    old_name = Path(old_avatar).name
    if not old_name or old_name == keep:
        return
    try:
        (AVATAR_DIR / old_name).unlink(missing_ok=True)
    except OSError:
        logger.warning("avatar_cleanup_failed", extra={"file": old_name})


def _to_auth_user(user: User) -> AuthUser:
    return AuthUser(
        id=user.id,
        email=user.email or "",
        name=user.display_name or user.email or "",
        role=user.role or "user",
        is_active=bool(user.is_active),
        avatar=user.avatar or "",
        created_at=_iso(user.created_at),
    )


def _iso(value: datetime.datetime | None) -> str | None:
    return value.isoformat() if value else None
