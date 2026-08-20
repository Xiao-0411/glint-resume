import datetime
import hmac
import hashlib
import re
import secrets
import smtplib
from email.message import EmailMessage
from email.utils import formataddr
from typing import Optional

from sqlalchemy.orm import Session as DBSession

from app.core.config import settings
from app.models.db_models import EmailVerificationCode


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PURPOSE_REGISTER = "register"


def _utcnow_naive() -> datetime.datetime:
    """Return UTC without tzinfo for MySQL ``DATETIME`` columns."""
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


def _as_utc_naive(value: datetime.datetime) -> datetime.datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(datetime.timezone.utc).replace(tzinfo=None)


class EmailCodeCooldownError(Exception):
    def __init__(self, retry_after: int):
        super().__init__("Email code cooldown")
        self.retry_after = retry_after


class EmailNotConfiguredError(Exception):
    pass


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def is_valid_email(email: str) -> bool:
    return bool(EMAIL_RE.match(normalize_email(email)))


def create_and_send_code(
    db: DBSession,
    email: str,
    purpose: str = PURPOSE_REGISTER,
) -> dict:
    email = normalize_email(email)
    now = _utcnow_naive()

    latest = (
        db.query(EmailVerificationCode)
        .filter(
            EmailVerificationCode.email == email,
            EmailVerificationCode.purpose == purpose,
        )
        .order_by(EmailVerificationCode.sent_at.desc(), EmailVerificationCode.created_at.desc())
        .first()
    )
    if latest and latest.sent_at:
        elapsed = int((now - _as_utc_naive(latest.sent_at)).total_seconds())
        if elapsed < settings.EMAIL_CODE_COOLDOWN_SECONDS:
            raise EmailCodeCooldownError(settings.EMAIL_CODE_COOLDOWN_SECONDS - elapsed)

    code = f"{secrets.randbelow(1000000):06d}"
    expires_at = now + datetime.timedelta(minutes=settings.EMAIL_CODE_EXPIRE_MINUTES)

    if settings.smtp_available:
        _send_email_code(email, code, expires_at)
        dev_code: Optional[str] = None
    elif settings.EMAIL_VERIFICATION_DEV_MODE:
        dev_code = code
    else:
        raise EmailNotConfiguredError()

    row = EmailVerificationCode(
        email=email,
        purpose=purpose,
        code_hash=_hash_code(email, purpose, code),
        expires_at=expires_at,
        sent_at=now,
    )
    db.add(row)
    db.commit()

    return {
        "expires_in_seconds": settings.EMAIL_CODE_EXPIRE_MINUTES * 60,
        "cooldown_seconds": settings.EMAIL_CODE_COOLDOWN_SECONDS,
        "dev_code": dev_code,
    }


def verify_code(
    db: DBSession,
    email: str,
    code: str,
    purpose: str = PURPOSE_REGISTER,
) -> bool:
    email = normalize_email(email)
    code = (code or "").strip()
    now = _utcnow_naive()

    row = (
        db.query(EmailVerificationCode)
        .filter(
            EmailVerificationCode.email == email,
            EmailVerificationCode.purpose == purpose,
            EmailVerificationCode.used_at.is_(None),
            EmailVerificationCode.expires_at >= now,
        )
        .order_by(EmailVerificationCode.created_at.desc())
        .first()
    )
    if row is None:
        return False

    expected_hash = _hash_code(email, purpose, code)
    if not hmac.compare_digest(row.code_hash, expected_hash):
        return False

    row.used_at = now
    db.commit()
    return True


def _hash_code(email: str, purpose: str, code: str) -> str:
    message = f"{email}:{purpose}:{code}".encode("utf-8")
    return hmac.new(
        settings.AUTH_SECRET_KEY.encode("utf-8"),
        message,
        hashlib.sha256,
    ).hexdigest()


def _send_email_code(email: str, code: str, expires_at: datetime.datetime):
    beijing_tz = datetime.timezone(datetime.timedelta(hours=8))
    expires_at_beijing = expires_at.replace(tzinfo=datetime.timezone.utc).astimezone(beijing_tz)
    msg = EmailMessage()
    msg["Subject"] = "识光简历邮箱验证码"
    msg["From"] = formataddr((settings.SMTP_FROM_NAME, settings.SMTP_FROM))
    msg["To"] = email
    msg.set_content(
        "\n".join([
            "你正在注册识光简历账号。",
            "",
            f"验证码：{code}",
            f"有效期至北京时间：{expires_at_beijing.strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "如果不是你本人操作，请忽略这封邮件。",
        ])
    )

    if settings.SMTP_USE_SSL:
        with smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as server:
            _login_if_needed(server)
            server.send_message(msg)
    else:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as server:
            server.starttls()
            _login_if_needed(server)
            server.send_message(msg)


def _login_if_needed(server):
    if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
        server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
