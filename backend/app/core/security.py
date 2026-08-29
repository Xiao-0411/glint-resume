import base64
import datetime
import hashlib
import hmac
import json
import os
from zoneinfo import ZoneInfo
from typing import Any, Dict

from app.core.config import settings


PASSWORD_SCHEME = "pbkdf2_sha256"
PASSWORD_ITERATIONS = 260000
DAILY_AUTH_RESET_HOUR = 4
AUTH_RESET_TIMEZONE = ZoneInfo("Asia/Shanghai")


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PASSWORD_ITERATIONS,
    )
    return "$".join([
        PASSWORD_SCHEME,
        str(PASSWORD_ITERATIONS),
        _b64encode(salt),
        _b64encode(digest),
    ])


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        scheme, iterations_raw, salt_raw, digest_raw = stored_hash.split("$", 3)
        if scheme != PASSWORD_SCHEME:
            return False
        salt = _b64decode(salt_raw)
        expected = _b64decode(digest_raw)
        actual = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            int(iterations_raw),
        )
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def next_daily_auth_reset(now: datetime.datetime | None = None) -> datetime.datetime:
    """Return the next 04:00 boundary in UTC (the policy timezone is Beijing)."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=datetime.timezone.utc)
    local_now = now.astimezone(AUTH_RESET_TIMEZONE)
    next_reset = local_now.replace(
        hour=DAILY_AUTH_RESET_HOUR,
        minute=0,
        second=0,
        microsecond=0,
    )
    if next_reset <= local_now:
        next_reset += datetime.timedelta(days=1)
    return next_reset.astimezone(datetime.timezone.utc)


def create_access_token(user_id: str) -> str:
    now = datetime.datetime.now(datetime.timezone.utc)
    configured_expire = now + datetime.timedelta(minutes=settings.AUTH_TOKEN_EXPIRE_MINUTES)
    # 令牌最长只保留到北京时间次日 04:00，确保旧令牌无法跨每日登录周期继续使用。
    expire = min(configured_expire, next_daily_auth_reset(now))
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": user_id,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    signing_input = ".".join([
        _json_b64encode(header),
        _json_b64encode(payload),
    ])
    signature = hmac.new(
        settings.AUTH_SECRET_KEY.encode("utf-8"),
        signing_input.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{signing_input}.{_b64encode(signature)}"


def decode_access_token(token: str) -> Dict[str, Any]:
    try:
        header_raw, payload_raw, signature_raw = token.split(".", 2)
    except ValueError as exc:
        raise ValueError("Invalid token") from exc

    signing_input = f"{header_raw}.{payload_raw}"
    expected_signature = hmac.new(
        settings.AUTH_SECRET_KEY.encode("utf-8"),
        signing_input.encode("ascii"),
        hashlib.sha256,
    ).digest()
    actual_signature = _b64decode(signature_raw)
    if not hmac.compare_digest(actual_signature, expected_signature):
        raise ValueError("Invalid token signature")

    header = json.loads(_b64decode(header_raw))
    if header.get("alg") != "HS256":
        raise ValueError("Unsupported token algorithm")

    payload = json.loads(_b64decode(payload_raw))
    exp = payload.get("exp")
    if not isinstance(exp, int) or exp <= int(datetime.datetime.now(datetime.timezone.utc).timestamp()):
        raise ValueError("Token expired")
    if not payload.get("sub"):
        raise ValueError("Token subject missing")
    return payload


def _json_b64encode(value: Dict[str, Any]) -> str:
    return _b64encode(
        json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    )


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))
