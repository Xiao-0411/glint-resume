import time
import uuid
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession

from app.core.auth_deps import get_current_user
from app.core.database import get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.models.db_models import User
from app.models.schemas import (
    AuthLoginRequest,
    AuthRegisterRequest,
    AuthResponse,
    AuthUser,
    EmailCodeRequest,
    EmailCodeResponse,
)
from app.services.email_verification_service import (
    EmailCodeCooldownError,
    EmailNotConfiguredError,
    PURPOSE_REGISTER,
    create_and_send_code,
    is_valid_email,
    normalize_email,
    verify_code,
)

router = APIRouter()

PASSWORD_POLICY_MESSAGE = "密码至少 8 位，且必须包含大写字母、小写字母和数字"

# ====== 暴力破解防护 ======
# 登录失败计数: {ip_or_account: [(timestamp, ...)]}
_login_failures: dict = defaultdict(list)
_LOGIN_MAX_FAILURES = 5       # 连续失败次数上限
_LOGIN_LOCKOUT_SECONDS = 300  # 锁定时长 5 分钟

# 验证码尝试计数: {email: [(timestamp, ...)]}
_code_attempts: dict = defaultdict(list)
_CODE_MAX_ATTEMPTS = 5        # 单个验证码最多尝试次数
_CODE_LOCKOUT_SECONDS = 600   # 锁定时长 10 分钟


def _check_login_brute_force(account: str, request: Request):
    """检查登录暴力破解，超限则拒绝"""
    key = f"login:{request.client.host if request.client else 'unknown'}"
    now = time.time()
    attempts = _login_failures[key]
    # 清理过期记录
    attempts[:] = [t for t in attempts if now - t < _LOGIN_LOCKOUT_SECONDS]
    if len(attempts) >= _LOGIN_MAX_FAILURES:
        remaining = int(_LOGIN_LOCKOUT_SECONDS - (now - attempts[0]))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"登录尝试过于频繁，请 {remaining} 秒后再试",
        )


def _record_login_failure(account: str, request: Request):
    key = f"login:{request.client.host if request.client else 'unknown'}"
    _login_failures[key].append(time.time())


def _clear_login_failures(account: str, request: Request):
    key = f"login:{request.client.host if request.client else 'unknown'}"
    _login_failures.pop(key, None)


def _check_code_brute_force(email: str):
    """检查验证码暴力破解"""
    now = time.time()
    attempts = _code_attempts[email]
    attempts[:] = [t for t in attempts if now - t < _CODE_LOCKOUT_SECONDS]
    if len(attempts) >= _CODE_MAX_ATTEMPTS:
        remaining = int(_CODE_LOCKOUT_SECONDS - (now - attempts[0]))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"验证码尝试过于频繁，请 {remaining} 秒后再试",
        )


def _record_code_attempt(email: str):
    _code_attempts[email].append(time.time())


def _clear_code_attempts(email: str):
    _code_attempts.pop(email, None)


@router.post("/auth/email-code/send", response_model=EmailCodeResponse)
def send_email_code(req: EmailCodeRequest, db: DBSession = Depends(get_db)):
    email = normalize_email(req.email)
    if not is_valid_email(email):
        raise HTTPException(status_code=400, detail="请输入有效邮箱")

    exists = db.query(User).filter(User.email == email).first()
    if exists:
        raise HTTPException(status_code=409, detail="该邮箱已注册，请直接登录")

    try:
        result = create_and_send_code(db, email, PURPOSE_REGISTER)
    except EmailCodeCooldownError as exc:
        raise HTTPException(
            status_code=429,
            detail=f"验证码发送过于频繁，请 {exc.retry_after} 秒后再试",
        )
    except EmailNotConfiguredError:
        raise HTTPException(
            status_code=503,
            detail="邮件服务未配置，请联系管理员",
        )
    except Exception:
        raise HTTPException(status_code=502, detail="验证码发送失败，请稍后重试")

    return EmailCodeResponse(
        message="验证码已发送，请查收邮箱",
        expires_in_seconds=result["expires_in_seconds"],
        cooldown_seconds=result["cooldown_seconds"],
        dev_code=result.get("dev_code"),
    )


@router.post("/auth/register", response_model=AuthResponse)
def register(req: AuthRegisterRequest, db: DBSession = Depends(get_db)):
    account = normalize_email(req.account)
    if not account:
        raise HTTPException(status_code=400, detail="请输入有效账号")
    if not is_valid_email(account):
        raise HTTPException(status_code=400, detail="请输入有效邮箱")
    _validate_password_policy(req.password)

    exists = db.query(User).filter(User.email == account).first()
    if exists:
        raise HTTPException(status_code=409, detail="账号已存在，请直接登录")

    # 验证码暴力破解检查
    _check_code_brute_force(account)
    if not verify_code(db, account, req.verification_code, PURPOSE_REGISTER):
        _record_code_attempt(account)
        raise HTTPException(status_code=400, detail="验证码错误或已过期")
    _clear_code_attempts(account)

    display_name = (req.display_name or "").strip() or _display_name_from_account(account)
    user = User(
        id=uuid.uuid4().hex,
        email=account,
        display_name=display_name,
        password_hash=hash_password(req.password),
        role="user",
        is_active=True,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="账号已存在，请直接登录")
    db.refresh(user)
    return _auth_response(user)


@router.post("/auth/login", response_model=AuthResponse)
def login(req: AuthLoginRequest, request: Request, db: DBSession = Depends(get_db)):
    account = normalize_email(req.account)

    # 暴力破解检查
    _check_login_brute_force(account, request)

    user = db.query(User).filter(User.email == account).first()
    if not user or not user.password_hash or not verify_password(req.password, user.password_hash):
        _record_login_failure(account, request)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="账号或密码错误",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账号已被禁用，请联系管理员",
        )

    _clear_login_failures(account, request)
    return _auth_response(user)


@router.get("/auth/me", response_model=AuthUser)
def me(current_user: User = Depends(get_current_user)):
    return _to_auth_user(current_user)


def _auth_response(user: User) -> AuthResponse:
    return AuthResponse(
        token=create_access_token(user.id),
        token_type="bearer",
        user=_to_auth_user(user),
    )


def _to_auth_user(user: User) -> AuthUser:
    return AuthUser(
        id=user.id,
        email=user.email or "",
        name=user.display_name or user.email or "",
        role=user.role or "user",
        is_active=bool(user.is_active),
        avatar=user.avatar or "",
        created_at=user.created_at.isoformat() if user.created_at else None,
    )

def _display_name_from_account(account: str) -> str:
    return account.split("@", 1)[0] if "@" in account else account


def _validate_password_policy(password: str):
    if (
        len(password) < 8
        or not any(ch.isupper() for ch in password)
        or not any(ch.islower() for ch in password)
        or not any(ch.isdigit() for ch in password)
    ):
        raise HTTPException(status_code=400, detail=PASSWORD_POLICY_MESSAGE)
