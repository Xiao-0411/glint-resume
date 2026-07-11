"""
识光简历 (Glint) 后端入口
启动:  uvicorn main:app --reload --port 8000
"""
import logging
import time
from collections import defaultdict, deque

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.database import init_db
from app.core.logging_config import setup_logging
from app.api import admin, auth, chat, resume, evaluation, jobs, sessions, usage

# 结构化日志初始化
setup_logging(level=settings.LOG_LEVEL)
logger = logging.getLogger("glint")

# Sentry 错误追踪（可选，配置 SENTRY_DSN 后启用）
if settings.SENTRY_DSN:
    import sentry_sdk
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.SENTRY_ENVIRONMENT,
        traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
    )
    logger.info("sentry_initialized", extra={
        "environment": settings.SENTRY_ENVIRONMENT,
        "traces_sample_rate": settings.SENTRY_TRACES_SAMPLE_RATE,
    })

app = FastAPI(
    title="识光简历 (Glint) API",
    version="0.1.0",
    description="识光简历 —— 用 AI 识出你不曾察觉的闪光点，简历锻造与质量评估后端"
)

# 启动时自动建表
init_db()

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


# ====== 安全响应头中间件 ======
@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "font-src 'self'; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )
    return response


# 双重限流: 用户 ID + 客户端 IP
# 默认关闭(RATE_LIMIT_PER_MIN=0),本地 demo 完全不受影响;
# 公网部署时设环境变量 RATE_LIMIT_PER_MIN=60 等即可启用。
_rate_buckets: dict = defaultdict(deque)


def _rate_limit_key(request: Request) -> str:
    """组合 user_id + IP 作为限流 key，防止代理绕过纯 IP 限流。"""
    ip = request.client.host if request.client else "unknown"
    # 尝试从 Authorization header 提取 user_id（不依赖 DB 查询，轻量）
    user_id = "anon"
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        try:
            from app.core.security import decode_access_token
            payload = decode_access_token(auth_header[7:])
            user_id = payload.get("sub", "anon")
        except Exception:
            user_id = f"anon@{ip}"
    return f"{user_id}|{ip}"


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    limit = settings.RATE_LIMIT_PER_MIN
    if limit > 0 and request.method == "POST" and request.url.path.startswith("/api/"):
        key = _rate_limit_key(request)
        now = time.time()
        bucket = _rate_buckets[key]
        while bucket and now - bucket[0] > 60:
            bucket.popleft()
        if len(bucket) >= limit:
            logger.warning("rate_limit_exceeded", extra={
                "key": key,
                "path": request.url.path,
                "ip": request.client.host if request.client else "unknown",
            })
            return JSONResponse(
                status_code=429,
                content={"detail": "请求过于频繁,请稍后再试"}
            )
        bucket.append(now)
    return await call_next(request)

app.include_router(auth.router, prefix="/api", tags=["auth"])
app.include_router(admin.router, prefix="/api", tags=["admin"])
app.include_router(sessions.router, prefix="/api", tags=["sessions"])
app.include_router(usage.router, prefix="/api", tags=["usage"])
app.include_router(chat.router, prefix="/api", tags=["chat"])
app.include_router(resume.router, prefix="/api", tags=["resume"])
app.include_router(evaluation.router, prefix="/api", tags=["evaluation"])
app.include_router(jobs.router, prefix="/api", tags=["jobs"])


@app.get("/")
def root():
    return {
        "service": "识光简历 (Glint) API",
        "version": "0.1.0",
        "llm_available": settings.llm_available,
        "use_mock": settings.USE_MOCK,
        "model": settings.LLM_MODEL if settings.llm_available else "mock"
    }


@app.get("/api/health")
def health():
    return {"status": "ok", "llm_available": settings.llm_available}
