"""
数据库连接管理 —— SQLAlchemy 2.0 + MySQL
"""
import logging

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from app.core.config import settings

logger = logging.getLogger("glint.database")

engine = create_engine(
    settings.DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    # 简历生成要串行等多次 LLM 调用（实测可达 4 分钟），期间连接一直闲置。
    # pool_pre_ping 只在取连接时校验，救不了"持有期间被 MySQL 掐断"，
    # 所以按小于 MySQL wait_timeout 的周期主动回收。
    pool_recycle=280,
    echo=False,
    future=True
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI 依赖注入用"""
    db = SessionLocal()
    try:
        yield db
    finally:
        # 简历生成等接口会在依赖持有连接期间等待数分钟的 LLM 调用,
        # 期间连接闲置超过 MySQL wait_timeout 就已被服务端关闭。
        # 此时 close() 自身会抛 OperationalError,把一个已经成功的响应变成 500。
        try:
            db.close()
        except Exception:
            logger.warning("db_close_failed_after_idle", exc_info=True)


def init_db():
    """创建所有表 —— 启动时调用一次即可"""
    import app.models.db_models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _ensure_schema_updates()
    _ensure_jobs_unique_index()


def _ensure_schema_updates():
    inspector = inspect(engine)
    if "users" not in inspector.get_table_names():
        return

    user_columns = {column["name"] for column in inspector.get_columns("users")}
    with engine.begin() as conn:
        if "password_hash" not in user_columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN password_hash VARCHAR(255) NULL"))
        if "role" not in user_columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN role VARCHAR(32) NOT NULL DEFAULT 'user'"))
            conn.execute(text("CREATE INDEX ix_users_role ON users (role)"))
        if "is_active" not in user_columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN is_active TINYINT(1) NOT NULL DEFAULT 1"))
            conn.execute(text("CREATE INDEX ix_users_is_active ON users (is_active)"))
        if "avatar" not in user_columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN avatar VARCHAR(512) NULL"))

    _ensure_super_admin()


def _ensure_jobs_unique_index():
    """给 jobs 补 (platform, platform_job_id) 唯一索引。

    create_all 不会修改已存在的表，所以老库拿不到模型里新加的约束。
    爬虫按这两列做 upsert，没有唯一索引时并发写会留下重复职位。
    """
    inspector = inspect(engine)
    if "jobs" not in inspector.get_table_names():
        return
    index_name = "uq_jobs_platform_job"
    try:
        # 新库由 create_all 建成表级 UNIQUE 约束，老库迁移后是唯一索引，两处都要查，
        # 否则每次启动都会重复执行下面的 DDL。
        existing = {idx["name"] for idx in inspector.get_indexes("jobs")}
        existing |= {uc["name"] for uc in inspector.get_unique_constraints("jobs")}
    except Exception as exc:
        logger.warning("jobs_index_inspect_failed", extra={"error": str(exc)})
        return
    if index_name in existing:
        return
    try:
        with engine.begin() as conn:
            # 建唯一索引前先清掉历史重复行，每组只留 id 最大的那条。
            # 多表 DELETE 是 MySQL 语法，其它方言用等价子查询。
            if conn.dialect.name == "mysql":
                conn.execute(text(
                    "DELETE j FROM jobs j JOIN ("
                    "  SELECT platform, platform_job_id, MAX(id) AS keep_id FROM jobs"
                    "  GROUP BY platform, platform_job_id HAVING COUNT(*) > 1"
                    ") d ON j.platform = d.platform AND j.platform_job_id = d.platform_job_id"
                    " AND j.id <> d.keep_id"
                ))
            else:
                conn.execute(text(
                    "DELETE FROM jobs WHERE id NOT IN ("
                    "  SELECT MAX(id) FROM jobs GROUP BY platform, platform_job_id"
                    ")"
                ))
            conn.execute(text(
                f"CREATE UNIQUE INDEX {index_name} ON jobs (platform, platform_job_id)"
            ))
        logger.info("jobs_unique_index_created")
    except Exception as exc:
        # 没建上不影响功能，只是失去重复保护，不该拦住服务启动
        logger.warning("jobs_unique_index_failed", extra={"error": str(exc)})


def _ensure_super_admin():
    if not settings.SUPER_ADMIN_EMAIL or not settings.SUPER_ADMIN_PASSWORD:
        return

    from app.core.security import hash_password
    from app.models.db_models import User

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == settings.SUPER_ADMIN_EMAIL).first()
        if user is None:
            import uuid

            user = User(
                id=uuid.uuid4().hex,
                email=settings.SUPER_ADMIN_EMAIL,
                display_name=settings.SUPER_ADMIN_DISPLAY_NAME,
            )
            db.add(user)

        user.display_name = settings.SUPER_ADMIN_DISPLAY_NAME or user.display_name
        user.password_hash = hash_password(settings.SUPER_ADMIN_PASSWORD)
        user.role = "super_admin"
        user.is_active = True
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.error("ensure_super_admin_failed", extra={"error": str(exc)})
    finally:
        db.close()
