from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session as DBSession

from app.core.auth_deps import (
    ROLE_ADMIN,
    ROLE_SUPER_ADMIN,
    ROLE_USER,
    get_admin_user,
)
from app.core.database import get_db
from app.models.db_models import User
from app.models.schemas import AdminUserItem, AdminUserUpdateRequest

router = APIRouter()

MANAGEABLE_ROLES = {ROLE_USER, ROLE_ADMIN}


@router.get("/admin/users")
def list_users(
    role: str = Query("", description="user/admin，留空表示按当前管理员权限返回"),
    keyword: str = Query("", description="邮箱或昵称关键字"),
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_admin_user),
    db: DBSession = Depends(get_db),
):
    query = db.query(User)

    allowed_roles = _allowed_target_roles(current_user)
    if role:
        if role not in allowed_roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权查看该角色账号")
        query = query.filter(User.role == role)
    else:
        query = query.filter(User.role.in_(allowed_roles))

    kw = keyword.strip()
    if kw:
        like = f"%{kw}%"
        query = query.filter(or_(User.email.like(like), User.display_name.like(like)))

    total = query.count()
    rows = (
        query.order_by(User.created_at.desc(), User.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {
        "users": [_to_admin_user_item(row) for row in rows],
        "total": total,
    }


@router.patch("/admin/users/{user_id}")
def update_user(
    user_id: str,
    req: AdminUserUpdateRequest,
    current_user: User = Depends(get_admin_user),
    db: DBSession = Depends(get_db),
):
    target = db.query(User).filter(User.id == user_id).first()
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="账号不存在")
    _assert_can_manage(current_user, target)

    if req.display_name is not None:
        target.display_name = req.display_name.strip()

    if req.is_active is not None:
        if target.role == ROLE_SUPER_ADMIN:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="不能禁用超级管理员")
        target.is_active = req.is_active

    if req.role is not None:
        _update_role(current_user, target, req.role)

    db.commit()
    db.refresh(target)
    return {"user": _to_admin_user_item(target)}


@router.delete("/admin/users/{user_id}")
def delete_user(
    user_id: str,
    current_user: User = Depends(get_admin_user),
    db: DBSession = Depends(get_db),
):
    target = db.query(User).filter(User.id == user_id).first()
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="账号不存在")
    _assert_can_manage(current_user, target)
    if target.id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能删除自己")
    if target.role == ROLE_SUPER_ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="不能删除超级管理员")

    db.delete(target)
    db.commit()
    return {"ok": True}


def _allowed_target_roles(current_user: User):
    if current_user.role == ROLE_SUPER_ADMIN:
        return {ROLE_USER, ROLE_ADMIN}
    if current_user.role == ROLE_ADMIN:
        return {ROLE_USER}
    return set()


def _assert_can_manage(actor: User, target: User):
    if target.role == ROLE_SUPER_ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="超级管理员账号不能被管理")
    if actor.role == ROLE_SUPER_ADMIN and target.role in MANAGEABLE_ROLES:
        return
    if actor.role == ROLE_ADMIN and target.role == ROLE_USER:
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权管理该账号")


def _update_role(actor: User, target: User, new_role: str):
    if new_role not in {ROLE_USER, ROLE_ADMIN}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="角色不合法")
    if actor.role != ROLE_SUPER_ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="只有超级管理员能修改角色")
    if target.role == ROLE_SUPER_ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="不能修改超级管理员角色")
    target.role = new_role


def _to_admin_user_item(user: User) -> AdminUserItem:
    return AdminUserItem(
        id=user.id,
        email=user.email or "",
        name=user.display_name or user.email or "",
        role=user.role or ROLE_USER,
        is_active=bool(user.is_active),
        created_at=user.created_at.isoformat() if user.created_at else None,
        updated_at=user.updated_at.isoformat() if user.updated_at else None,
    )
