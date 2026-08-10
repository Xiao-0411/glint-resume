"""
应用配置 —— 全部从环境变量读取,通过 python-dotenv 加载 .env
"""
import logging
import os
from functools import lru_cache
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # LLM
    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "https://docs.newapi.pro/v1").rstrip("/")
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "deepseek-v4-pro")
    # 实时对话用的快模型：牺牲一点质量换首字节延迟，对话体验优先
    LLM_MODEL_FAST: str = os.getenv("LLM_MODEL_FAST", "deepseek-v4-flash")
    LLM_ANTHROPIC_VERSION: str = os.getenv("LLM_ANTHROPIC_VERSION", "2023-06-01")
    LLM_MAX_TOKENS: int = int(os.getenv("LLM_MAX_TOKENS", "2048"))
    LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.7"))
    # 单次请求超时：pro 实测单次 70~115s（网关较慢），给到 180s 避免正常请求被误杀；
    # 前端 240s 超时，留出兜底与响应回传的余量。
    LLM_TIMEOUT_SECONDS: float = float(os.getenv("LLM_TIMEOUT_SECONDS", "180"))
    LLM_TIMEOUT_FAST_SECONDS: float = float(os.getenv("LLM_TIMEOUT_FAST_SECONDS", "45"))
    # 网关偶发 5xx/超时，重试一次即可救回大部分请求
    LLM_MAX_RETRIES: int = int(os.getenv("LLM_MAX_RETRIES", "1"))
    LLM_USAGE_ENABLED: bool = os.getenv("LLM_USAGE_ENABLED", "true").lower() == "true"
    LLM_DAILY_CALL_LIMIT_PER_USER: int = int(os.getenv("LLM_DAILY_CALL_LIMIT_PER_USER", "100"))
    LLM_DAILY_TOKEN_LIMIT_PER_USER: int = int(os.getenv("LLM_DAILY_TOKEN_LIMIT_PER_USER", "200000"))
    LLM_DAILY_COST_LIMIT_USD_PER_USER: float = float(os.getenv("LLM_DAILY_COST_LIMIT_USD_PER_USER", "5"))
    LLM_INPUT_PRICE_PER_1M_USD: float = float(os.getenv("LLM_INPUT_PRICE_PER_1M_USD", "0"))
    LLM_OUTPUT_PRICE_PER_1M_USD: float = float(os.getenv("LLM_OUTPUT_PRICE_PER_1M_USD", "0"))

    # App
    USE_MOCK: bool = os.getenv("USE_MOCK", "false").lower() == "true"
    # 运行环境:development=本地开发,production=公网部署。部署时务必设为 production。
    APP_ENV: str = os.getenv("APP_ENV", "development").strip().lower()
    CORS_ORIGINS: list = [
        o.strip() for o in os.getenv(
            "CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173"
        ).split(",") if o.strip()
    ]
    # 本地开发时 vite 端口会漂移(5173 被占则跳 5174/5175...),固定白名单会让
    # 预检直接 400,前端只能看到 axios 的 "Network Error"。开启后按正则放行任意
    # 本地端口,不必每次改 .env。仅在 APP_ENV=development 时生效。
    CORS_ALLOW_LOCAL_ANY_PORT: bool = os.getenv("CORS_ALLOW_LOCAL_ANY_PORT", "true").lower() == "true"
    PORT: int = int(os.getenv("PORT", "8000"))

    # Auth
    AUTH_SECRET_KEY: str = os.getenv("AUTH_SECRET_KEY", "")
    AUTH_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("AUTH_TOKEN_EXPIRE_MINUTES", "1440"))
    SUPER_ADMIN_EMAIL: str = os.getenv("SUPER_ADMIN_EMAIL", "").strip().lower()
    SUPER_ADMIN_PASSWORD: str = os.getenv("SUPER_ADMIN_PASSWORD", "")
    SUPER_ADMIN_DISPLAY_NAME: str = os.getenv("SUPER_ADMIN_DISPLAY_NAME", "超级管理员")
    EMAIL_CODE_EXPIRE_MINUTES: int = int(os.getenv("EMAIL_CODE_EXPIRE_MINUTES", "10"))
    EMAIL_CODE_COOLDOWN_SECONDS: int = int(os.getenv("EMAIL_CODE_COOLDOWN_SECONDS", "60"))
    EMAIL_VERIFICATION_DEV_MODE: bool = os.getenv("EMAIL_VERIFICATION_DEV_MODE", "false").lower() == "true"

    # SMTP email sender
    SMTP_HOST: str = os.getenv("SMTP_HOST", "")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "465"))
    SMTP_USERNAME: str = os.getenv("SMTP_USERNAME", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM: str = os.getenv("SMTP_FROM", "") or SMTP_USERNAME
    SMTP_FROM_NAME: str = os.getenv("SMTP_FROM_NAME", "识光简历")
    SMTP_USE_SSL: bool = os.getenv("SMTP_USE_SSL", "true").lower() == "true"

    # 限流:每个 IP 每分钟允许的 /api POST 请求数。0 = 关闭(默认,本地 demo 不受影响)。
    # 公网部署时设为 >0(如 60),防止 /api/chat 等被刷爆 LLM 费用。
    RATE_LIMIT_PER_MIN: int = int(os.getenv("RATE_LIMIT_PER_MIN", "30"))

    # Sentry 错误追踪
    SENTRY_DSN: str = os.getenv("SENTRY_DSN", "")
    SENTRY_ENVIRONMENT: str = os.getenv("SENTRY_ENVIRONMENT", "production")
    SENTRY_TRACES_SAMPLE_RATE: float = float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1"))

    # 日志级别
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    # MySQL 数据库连接
    # 格式: mysql+pymysql://用户名:密码@主机:端口/数据库名?charset=utf8mb4
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "mysql+pymysql://root:123456@localhost:3306/glint?charset=utf8mb4"
    )

    @property
    def llm_available(self) -> bool:
        """Key 已配置且未启用强制 mock"""
        return bool(self.LLM_API_KEY) and not self.USE_MOCK

    @property
    def smtp_available(self) -> bool:
        return bool(self.SMTP_HOST and self.SMTP_PORT and self.SMTP_FROM)

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def has_public_origin(self) -> bool:
        """CORS 白名单里出现非本地来源,视为生产部署。"""
        return any(
            o.strip() and "localhost" not in o and "127.0.0.1" not in o
            for o in self.CORS_ORIGINS
        )

    @property
    def cors_origin_regex(self) -> str | None:
        """
        允许任意本地端口的正则。Starlette 用 fullmatch 匹配,所以
        http://localhost.evil.com 这类后缀伪装不会命中。

        只在 APP_ENV=development 时启用 —— 生产环境放行 localhost 等于给
        攻击者本机页面开了带凭证请求的口子(allow_credentials=True)。
        这里按 APP_ENV 而非"白名单里有没有公网域名"判定:本地 .env 常年
        带着生产域名做参考,按域名判定会误伤本地开发。
        """
        if self.is_production or not self.CORS_ALLOW_LOCAL_ANY_PORT:
            return None
        return r"http://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?"


# 本地开发用的固定密钥。仅在 CORS 只允许 localhost 时启用,
# 一旦配置了公网域名就必须显式提供 AUTH_SECRET_KEY。
_DEV_FALLBACK_SECRET = "glint-local-dev-only-do-not-use-in-production"


def _validate_auth_secret(cfg: "Settings") -> None:
    """
    AUTH_SECRET_KEY 为空时,HMAC 会用空字节串照常签出 token —— 不报错,
    但任何人都能伪造。这属于"静默失效"的安全问题,必须启动时拦住。

    判定是否为生产:CORS 里出现了非 localhost 的来源。
    """
    if cfg.AUTH_SECRET_KEY:
        return

    if cfg.has_public_origin:
        raise RuntimeError(
            "AUTH_SECRET_KEY 未配置,但 CORS_ORIGINS 含公网域名。\n"
            "空密钥会让 JWT 可被任意伪造(登录形同虚设)。\n"
            "请在 backend/.env 中设置一个长随机字符串,例如:\n"
            "  python -c \"import secrets; print(secrets.token_urlsafe(48))\""
        )
    # 纯本地开发:用固定的开发密钥,并警告
    cfg.AUTH_SECRET_KEY = _DEV_FALLBACK_SECRET
    logging.getLogger("glint").warning(
        "auth_secret_key_missing_using_dev_fallback",
        extra={"hint": "仅本地开发可用;部署前务必配置 AUTH_SECRET_KEY"},
    )


@lru_cache()
def get_settings() -> Settings:
    cfg = Settings()
    _validate_auth_secret(cfg)
    return cfg


settings = get_settings()
