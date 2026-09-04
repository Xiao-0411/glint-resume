"""
Pydantic 数据模型 —— 所有前后端交互的请求/响应结构
"""
from typing import Optional, List, Dict, Any, Annotated, Literal
from pydantic import BaseModel, Field, model_validator


# ============ Auth ============

class EmailCodeRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255, description="邮箱")


class EmailCodeResponse(BaseModel):
    message: str
    expires_in_seconds: int
    cooldown_seconds: int
    dev_code: Optional[str] = None


class AuthRegisterRequest(BaseModel):
    account: str = Field(..., min_length=3, max_length=255, description="邮箱")
    verification_code: str = Field(..., min_length=4, max_length=12, description="邮箱验证码")
    password: str = Field(..., min_length=1, max_length=128, description="至少 8 位，且包含字母和数字")
    display_name: Optional[str] = Field(None, max_length=128)


class AuthLoginRequest(BaseModel):
    account: str = Field(..., min_length=3, max_length=255, description="用户名或邮箱")
    password: str = Field(..., min_length=1, max_length=128)


class AuthUser(BaseModel):
    id: str
    email: str = ""
    name: str = ""
    role: str = "user"
    is_active: bool = True
    avatar: str = ""
    created_at: Optional[str] = None


class ProfileUpdateRequest(BaseModel):
    display_name: Optional[str] = Field(None, max_length=128)
    avatar: Optional[str] = Field(None, max_length=512)


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., min_length=1, max_length=128)


class ProfileStats(BaseModel):
    resume_count: int = 0
    best_score: Optional[int] = None
    average_score: Optional[float] = None
    application_count: int = 0
    interview_count: int = 0
    last_resume_at: Optional[str] = None


class AuthResponse(BaseModel):
    token: str
    token_type: str = "bearer"
    user: AuthUser


class AdminUserItem(BaseModel):
    id: str
    email: str = ""
    name: str = ""
    role: str = "user"
    is_active: bool = True
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class AdminUserUpdateRequest(BaseModel):
    display_name: Optional[str] = Field(None, max_length=128)
    role: Optional[str] = Field(None, description="user/admin，仅超级管理员可修改")
    is_active: Optional[bool] = None


# ============ Sessions ============

class AttachSessionRequest(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=64, description="要绑定到当前用户的会话 ID")
    target_job: str = Field("", max_length=100, description="会话目标岗位")


# ============ Chat ============

class ChatRequest(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=64, description="会话 ID,前端生成")
    user_id: Optional[str] = Field(None, description="用户 ID,未登录可不传")
    target_job: str = Field("", max_length=100, description="用户目标岗位")
    user_message: str = Field(..., min_length=1, max_length=4000, description="用户本轮输入")
    user_msg_count: int = Field(..., ge=1, le=1000, description="用户消息总数(含本条)")


class ChatResponseMeta(BaseModel):
    """非流式或流式末尾返回的元信息"""
    stage: str = Field(..., description="下一轮阶段")
    stage_label: str = Field("", description="阶段中文标签")
    quick_replies: List[str] = Field(default_factory=list)
    extracted_info: Optional[Dict[str, Any]] = None


class ChatCompleteResponse(BaseModel):
    """Validated non-streaming chat envelope returned to the frontend."""
    reply: str = Field(..., min_length=1)
    complete: Literal[True] = True
    stage: str
    stage_label: str = ""
    quick_replies: List[str] = Field(default_factory=list)
    extracted: Dict[str, Any] = Field(default_factory=dict)
    fallback: bool = False
    fallback_reason: str = ""


# ============ Resume ============

class GenerateResumeRequest(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=64)
    user_id: Optional[str] = None
    target_job: str = Field("", max_length=100)


class EvaluateTextRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=100_000, description="PDF 解析后的简历文本")
    file_name: str = Field("uploaded.pdf", max_length=255)
    session_id: Optional[str] = Field(None, min_length=1, max_length=64, description="当前会话 ID")
    user_id: Optional[str] = Field(None, description="用户 ID,未登录可不传")
    target_job: str = Field("", max_length=100, description="目标岗位")


class EvaluateResumeRequest(BaseModel):
    """对已有简历对象直接重评(用户编辑后)。保留其 exp_id,
    避免走"上传文本"管线重新生成简历导致 evidence/exp_id 与现有简历错位。"""
    resume: Dict[str, Any] = Field(..., max_length=20)
    target_job: str = Field("", max_length=100)
    session_id: Optional[str] = Field(None, min_length=1, max_length=64, description="当前会话 ID")
    user_id: Optional[str] = Field(None, description="用户 ID,未登录可不传")

    @model_validator(mode="after")
    def validate_resume_complexity(self):
        nodes = 0

        def walk(value, depth=0):
            nonlocal nodes
            nodes += 1
            if nodes > 5000:
                raise ValueError("简历内容过于复杂")
            if depth > 12:
                raise ValueError("简历嵌套层级过深")
            if isinstance(value, str) and len(value) > 20_000:
                raise ValueError("简历单个字段不能超过 20000 字符")
            if isinstance(value, list):
                if len(value) > 200:
                    raise ValueError("简历单个列表不能超过 200 项")
                for item in value:
                    walk(item, depth + 1)
            elif isinstance(value, dict):
                if len(value) > 100:
                    raise ValueError("简历单个对象不能超过 100 个字段")
                for key, item in value.items():
                    if len(str(key)) > 128:
                        raise ValueError("简历字段名过长")
                    walk(item, depth + 1)

        walk(self.resume)
        return self


class ResumeBasic(BaseModel):
    fullname: str = ""
    target_job: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""


class ResumeEducation(BaseModel):
    school: str = ""
    major: str = ""
    degree: str = ""
    period: str = ""
    gpa: str = ""
    highlights: List[str] = []


class ResumeExperienceTag(BaseModel):
    label: str = "基于真实经历重塑"
    level: str = "high"
    color: str = "green"


class ResumeExperience(BaseModel):
    id: str
    title: str
    type: str = "other"
    role: str = ""
    period: str = ""
    bullets: List[str] = []
    tag: ResumeExperienceTag = Field(default_factory=ResumeExperienceTag)


class ResumeSkills(BaseModel):
    technical: List[str] = []
    product: List[str] = []
    soft: List[str] = []


class ResumeData(BaseModel):
    basic: ResumeBasic
    education: List[ResumeEducation] = []
    experiences: List[ResumeExperience] = []
    skills: ResumeSkills = Field(default_factory=ResumeSkills)
    awards: List[str] = []
    self_evaluation: str = ""


# ============ Quality Report ============

class QualityDimension(BaseModel):
    name: str
    score: int
    max: int = 100
    desc: str = ""


class QualityHighlight(BaseModel):
    title: str
    score: int
    desc: str
    icon: str = "check"


class QualityImprovement(BaseModel):
    title: str
    score: int
    desc: str
    target_exp_id: Optional[str] = None
    evidence: str = ""
    actions: List[Dict[str, Any]] = []


class QualityReport(BaseModel):
    total_score: int
    grade: str
    grade_color: str
    dimensions: List[QualityDimension]
    highlights: List[QualityHighlight] = []
    improvements: List[QualityImprovement] = []
    action_guide: str = ""
    integrity_statement: str = ""
    from_upload: bool = False
    source_file: Optional[str] = None


# ============ Combined ============

class ResumeWithReport(BaseModel):
    resume: ResumeData
    quality_report: QualityReport


# ============ Jobs (求职加速) ============

class JobSearchRequest(BaseModel):
    keyword: str = Field("", max_length=100)
    target_job: str = Field("", max_length=100)
    provinces: List[Annotated[str, Field(min_length=1, max_length=64)]] = Field(default_factory=list, max_length=34)
    locations: List[Annotated[str, Field(min_length=1, max_length=64)]] = Field(default_factory=list, max_length=400)
    educations: List[Annotated[str, Field(min_length=1, max_length=32)]] = Field(default_factory=list, max_length=10)


class JobAdaptRequest(BaseModel):
    job_id: str = Field("", max_length=64)
    target_job: str = Field("", max_length=100)


class JobApplyRequest(BaseModel):
    job_id: str = Field("", max_length=64)
    resume_version: str = Field("original", max_length=32)


class ApplicationStatusRequest(BaseModel):
    application_id: str = Field("", max_length=64)
    status: str = Field("", max_length=32)
