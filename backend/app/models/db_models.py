"""
SQLAlchemy ORM models for MySQL persistence.
"""
import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text
from sqlalchemy.orm import relationship

from app.core.database import Base


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


class User(Base):
    """User ownership table.

    The anonymous user keeps guest sessions attachable, while registered users
    store only a password hash for authentication.
    """
    __tablename__ = "users"

    id = Column(String(64), primary_key=True)
    email = Column(String(255), unique=True, nullable=True, index=True)
    display_name = Column(String(128), default="")
    password_hash = Column(String(255), nullable=True)
    role = Column(String(32), nullable=False, default="user", index=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    sessions = relationship("Session", back_populates="user")
    resumes = relationship("Resume", back_populates="user")
    llm_usage_records = relationship("LLMUsageRecord", back_populates="user")


class EmailVerificationCode(Base):
    """One-time email verification code for account registration."""
    __tablename__ = "email_verification_codes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), nullable=False, index=True)
    purpose = Column(String(32), nullable=False, default="register", index=True)
    code_hash = Column(String(255), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)
    sent_at = Column(DateTime, default=_now)
    created_at = Column(DateTime, default=_now)


class Session(Base):
    """Conversation session, replacing the old in-memory dict."""
    __tablename__ = "sessions"

    id = Column(String(64), primary_key=True)
    user_id = Column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    target_job = Column(String(128), default="")
    stage = Column(String(32), default="basic_info")
    extracted = Column(JSON, default=dict)
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    user = relationship("User", back_populates="sessions")
    messages = relationship(
        "Message",
        back_populates="session",
        order_by="Message.created_at",
        cascade="all, delete-orphan",
    )


class Message(Base):
    """Conversation message."""
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(64), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(16), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=_now)

    session = relationship("Session", back_populates="messages")


class Resume(Base):
    """Generated resume and its quality report."""
    __tablename__ = "resumes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    session_id = Column(String(64), ForeignKey("sessions.id", ondelete="SET NULL"), nullable=True, index=True)
    target_job = Column(String(128), default="")
    resume_json = Column(JSON, default=dict)
    quality_report_json = Column(JSON, default=dict)
    total_score = Column(Integer, default=0)
    grade = Column(String(16), default="")
    source = Column(String(32), default="chat")
    created_at = Column(DateTime, default=_now)

    user = relationship("User", back_populates="resumes")
    session = relationship("Session")


class LLMUsageRecord(Base):
    """Per-call LLM token usage and estimated cost."""
    __tablename__ = "llm_usage_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    session_id = Column(String(64), ForeignKey("sessions.id", ondelete="SET NULL"), nullable=True, index=True)
    endpoint = Column(String(128), default="", index=True)
    source = Column(String(64), default="")
    model = Column(String(128), default="")
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)
    cost_usd = Column(Numeric(12, 6), default=0)
    status = Column(String(32), default="success", index=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_now, index=True)

    user = relationship("User", back_populates="llm_usage_records")
    session = relationship("Session")


class Application(Base):
    """Job application record — replaces the old mock_get_applications."""
    __tablename__ = "applications"

    id = Column(String(64), primary_key=True)
    user_id = Column(String(64), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    job_id = Column(String(64), nullable=False, index=True)
    job_title = Column(String(128), default="")
    company = Column(String(128), default="")
    resume_version = Column(String(32), default="original")
    status = Column(String(32), default="applied", index=True)
    status_label = Column(String(32), default="已投递")
    status_history = Column(JSON, default=list)
    applied_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)
    created_at = Column(DateTime, default=_now)

    user = relationship("User")


class Job(Base):
    """职位数据 - 爬虫抓取的真实职位"""
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    platform = Column(String(32), nullable=False, index=True, comment="平台: zhipin/zhaopin/liepin")
    platform_job_id = Column(String(128), nullable=False, index=True, comment="平台原始职位ID")
    title = Column(String(256), nullable=False, comment="职位名称")
    company = Column(String(256), nullable=False, comment="公司名称")
    salary = Column(String(64), default="", comment="薪资范围")
    location = Column(String(128), default="", comment="工作地点")
    experience = Column(String(64), default="", comment="经验要求")
    education = Column(String(64), default="", comment="学历要求")
    tags = Column(JSON, default=list, comment="标签")
    description = Column(Text, default="", comment="职位描述")
    requirements = Column(JSON, default=list, comment="职位要求（技能列表）")
    url = Column(String(512), default="", comment="原始链接")
    is_active = Column(Boolean, default=True, index=True, comment="是否有效")
    crawled_at = Column(DateTime, default=_now, comment="抓取时间")
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)
