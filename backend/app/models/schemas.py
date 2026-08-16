"""
Pydantic 数据模型 —— 所有前后端交互的请求/响应结构
"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


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
    session_id: str = Field(..., description="要绑定到当前用户的会话 ID")
    target_job: str = Field("", description="会话目标岗位")


# ============ Chat ============

class ChatRequest(BaseModel):
    session_id: str = Field(..., description="会话 ID,前端生成")
    user_id: Optional[str] = Field(None, description="用户 ID,未登录可不传")
    target_job: str = Field("", description="用户目标岗位")
    user_message: str = Field(..., description="用户本轮输入")
    user_msg_count: int = Field(..., description="用户消息总数(含本条)")


class ChatResponseMeta(BaseModel):
    """非流式或流式末尾返回的元信息"""
    stage: str = Field(..., description="下一轮阶段")
    stage_label: str = Field("", description="阶段中文标签")
    quick_replies: List[str] = Field(default_factory=list)
    extracted_info: Optional[Dict[str, Any]] = None


# ============ Resume ============

class GenerateResumeRequest(BaseModel):
    session_id: str
    user_id: Optional[str] = None
    target_job: str = ""


class EvaluateTextRequest(BaseModel):
    text: str = Field(..., description="PDF 解析后的简历文本")
    file_name: str = Field("uploaded.pdf")
    session_id: Optional[str] = Field(None, description="当前会话 ID")
    user_id: Optional[str] = Field(None, description="用户 ID,未登录可不传")
    target_job: str = Field("", description="目标岗位")


class EvaluateResumeRequest(BaseModel):
    """对已有简历对象直接重评(用户编辑后)。保留其 exp_id,
    避免走"上传文本"管线重新生成简历导致 evidence/exp_id 与现有简历错位。"""
    resume: Dict[str, Any]
    target_job: str = ""
    session_id: Optional[str] = Field(None, description="当前会话 ID")
    user_id: Optional[str] = Field(None, description="用户 ID,未登录可不传")


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
    keyword: str = ""
    target_job: str = ""


class JobAdaptRequest(BaseModel):
    job_id: str = ""
    target_job: str = ""


class JobApplyRequest(BaseModel):
    job_id: str = ""
    resume_version: str = "original"


class ApplicationStatusRequest(BaseModel):
    application_id: str = ""
    status: str = ""
