"""
POST /api/jobs/search  ——  职位搜索与匹配分级
GET  /api/jobs/detail/{job_id}  ——  按需获取完整岗位详情
POST /api/jobs/adapt  ——  简历动态适配
POST /api/jobs/apply  ——  一键投递（持久化到 MySQL）
GET  /api/jobs/applications  ——  获取投递列表（从 DB 读取）
POST /api/jobs/applications/status  ——  更新投递状态（持久化）

职位数据来自爬虫库（jobs 表）；库为空时按关键词实时抓取，不返回 mock 职位。
"""
import datetime
import logging
import re
import uuid
import asyncio
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session as DBSession

from app.core.auth_deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.models.db_models import Application, Job, User, CrawlerStatus
from app.models.schemas import (
    JobSearchRequest, JobAdaptRequest, JobApplyRequest, ApplicationStatusRequest
)
from app.mock.fallback import (
    mock_adapt_resume, mock_apply_job,
    KW_MAP,
)
from app.crawlers.scheduler import crawl_keyword
from app.crawlers.external_boss import ExternalBossCrawler
from app.crawlers.zhaopin import ZhaopinCrawler
from app.crawlers.liepin import LiepinCrawler
from app.services.location_catalog import cities_for_provinces, location_catalog

router = APIRouter()
logger = logging.getLogger("glint.jobs")


@router.get("/jobs/crawler-status")
async def crawler_status(current_user: User = Depends(get_current_user), db: DBSession = Depends(get_db)):
    """返回三个招聘渠道最近一次抓取状态。"""
    rows = {row.platform: row for row in db.query(CrawlerStatus).all()}
    platforms = {"zhipin": "BOSS直聘", "zhaopin": "智联招聘", "liepin": "猎聘"}
    data = []
    for platform, label in platforms.items():
        row = rows.get(platform)
        data.append({
            "platform": platform,
            "label": label,
            "status": row.status if row else "never",
            "lastStartedAt": row.last_started_at.isoformat() if row and row.last_started_at else "",
            "lastFinishedAt": row.last_finished_at.isoformat() if row and row.last_finished_at else "",
            "lastSuccessAt": row.last_success_at.isoformat() if row and row.last_success_at else "",
            "lastJobCount": row.last_job_count if row else 0,
            "lastSavedCount": row.last_saved_count if row else 0,
            "lastDurationMs": row.last_duration_ms if row else 0,
            "lastError": row.last_error if row else "",
        })
    return {"platforms": data}

STATUS_LABEL_MAP = {
    "applied": "已投递",
    "screened": "简历通过筛选",
    "interviewing": "面试邀约",
    "offered": "已获Offer",
    "rejected": "未通过筛选",
    "withdrawn": "已撤回",
}

CITY_NAMES = sorted(
    [city["value"] for province in location_catalog() for city in province["cities"]],
    key=len,
    reverse=True,
)


@router.get("/jobs/locations")
async def job_locations():
    """返回独立于职位库存量的全国省市筛选目录。"""
    return {"provinces": location_catalog()}


def _clean_title(value: str) -> str:
    """去掉岗位名尾部粘连的薪资，以及【】角标。

    角标常出现在开头（"【Python】后端开发工程师"），直接按【切分会得到空串，
    因此改为移除角标本身而不是截断其后的内容。
    """
    title = re.sub(r"\s+", " ", (value or "").strip())
    title = re.sub(r"【[^】]*】", " ", title)
    title = re.split(r"\s+(?=\d+(?:\.\d+)?\s*[-~至]\s*\d+(?:\.\d+)?\s*[kK千万元])", title, maxsplit=1)[0]
    return re.sub(r"\s+", " ", title)[:100].strip(" -|·")


def _clean_location(value: str) -> str:
    raw = (value or "").strip()
    city = next((name for name in CITY_NAMES if raw.startswith(name)), "")
    if not city:
        return raw or "全国"
    suffix = raw[len(city):]
    district = re.match(r"\s*[-·]\s*([\u4e00-\u9fff]{2,8}(?:区|县|市))", suffix)
    return f"{city}·{district.group(1)}" if district else city


def _db_job_search(
    keyword: str = "",
    locations: list[str] | None = None,
    educations: list[str] | None = None,
    db: DBSession = None,
    limit: int = 60,
) -> list:
    """从 MySQL jobs 表搜索职位"""
    if db is None:
        return []

    query = db.query(Job).filter(Job.is_active == True)
    locations = [value.strip() for value in (locations or []) if value.strip()]
    educations = [value.strip() for value in (educations or []) if value.strip()]

    if keyword:
        kw = f"%{keyword}%"
        # 岗位描述不再随列表抓取入库，按 description 搜索会漏掉绝大多数记录，
        # 因此只在岗位名/公司/地点上匹配。
        query = query.filter(
            or_(
                Job.title.like(kw),
                Job.company.like(kw),
                Job.location.like(kw),
            )
        )

    if locations:
        query = query.filter(or_(*(Job.location.like(f"%{value}%") for value in locations)))

    if educations:
        query = query.filter(or_(*(Job.education.like(f"%{value}%") for value in educations)))

    candidate_limit = min(max(limit * 8, limit), 500)
    rows = query.order_by(Job.crawled_at.desc(), Job.id.desc()).limit(candidate_limit).all()

    buckets = {}
    for row in rows:
        city = next((name for name in CITY_NAMES if (row.location or "").startswith(name)), "其他")
        buckets.setdefault(city, []).append(row)
    balanced_rows = []
    ordered_keys = [city for city in CITY_NAMES if city in buckets]
    if "其他" in buckets:
        ordered_keys.append("其他")
    while len(balanced_rows) < limit and any(buckets.get(city) for city in ordered_keys):
        for city in ordered_keys:
            if buckets.get(city):
                balanced_rows.append(buckets[city].pop(0))
                if len(balanced_rows) == limit:
                    break

    results = []
    for row in balanced_rows:
        results.append({
            "id": f"job_db_{row.id}",
            "title": _clean_title(row.title),
            "company": row.company,
            "salary": row.salary or "薪资面议",
            "location": _clean_location(row.location),
            "education": row.education or "学历不限",
            "tags": row.tags or [],
            "description": row.description if _has_full_detail(row) else "",
            "requirements": row.requirements or [],
            "platform": row.platform,
            "url": row.url or "",
            "category": row.category or "",
            "jobLevel": row.job_level or "",
            "industry": row.industry or "",
            "crawledAt": row.crawled_at.isoformat() if row.crawled_at else "",
        })
    return results


def _job_payload(row: Job, *, include_description: bool = True) -> dict:
    return {
        "id": f"job_db_{row.id}",
        "title": _clean_title(row.title),
        "company": row.company,
        "salary": row.salary or "薪资面议",
        "location": _clean_location(row.location),
        "experience": row.experience or "经验不限",
        "education": row.education or "学历不限",
        "tags": row.tags or [],
        "description": (row.description or "") if include_description else "",
        "requirements": row.requirements or [],
        "platform": row.platform,
        "url": row.url or "",
        "category": row.category or "",
        "jobLevel": row.job_level or "",
        "industry": row.industry or "",
        "crawledAt": row.crawled_at.isoformat() if row.crawled_at else "",
    }


def _has_full_detail(row: Job) -> bool:
    description = (row.description or "").strip()
    if len(description) < 120:
        return False
    # 旧版列表抓取曾把整张卡片写进 description：通常会同时重复岗位名、
    # 公司和薪资。即使文本很长，也不能视为已经抓取过的 JD。
    repeated_fields = [row.title, row.company, row.salary]
    if sum(bool(value and str(value).strip() in description) for value in repeated_fields) >= 2:
        return False
    if row.platform == "zhipin":
        return True
    return any(marker in description for marker in ("岗位职责", "职位职责", "任职要求", "职位要求", "职位描述"))


def _crawler_for_platform(platform: str):
    crawlers = {
        "zhipin": ExternalBossCrawler,
        "zhaopin": ZhaopinCrawler,
        "liepin": LiepinCrawler,
    }
    crawler_class = crawlers.get(platform)
    return crawler_class() if crawler_class else None


def _is_trusted_job_url(platform: str, url: str) -> bool:
    allowed_domains = {
        "zhipin": "zhipin.com",
        "zhaopin": "zhaopin.com",
        "liepin": "liepin.com",
    }
    domain = allowed_domains.get(platform)
    try:
        parsed = urlparse(url)
        hostname = (parsed.hostname or "").lower()
    except ValueError:
        return False
    return parsed.scheme == "https" and bool(domain) and (hostname == domain or hostname.endswith(f".{domain}"))


def _direction_score(target: str, title: str, synonyms: list[str]) -> tuple[int, str]:
    """岗位名方向契合度：0-100 与一句说明。"""
    title_lower, target_lower = title.lower(), target.lower()
    if target_lower in title_lower or title_lower in target_lower:
        return 100, f"岗位名与目标岗位「{target}」高度一致"
    hits = [word for word in synonyms if word.lower() in title_lower]
    if hits:
        return 78, f"岗位方向与「{'、'.join(hits[:3])}」相关"
    bigrams_target = {target_lower[i:i + 2] for i in range(len(target_lower) - 1)}
    bigrams_title = {title_lower[i:i + 2] for i in range(len(title_lower) - 1)}
    if bigrams_target & bigrams_title:
        # 中文岗位名共享 2 字片段（如"产品经理"↔"产品运营"）视为部分相关。
        return 60, "岗位方向部分相关"
    return 20, "岗位方向与目标岗位差异较大"


def _calc_match(target_job: str, job: dict) -> dict:
    """计算岗位匹配度。

    判据优先级：
    1. 岗位有真实技能清单（来自 JD 抓取 + AI 提取）时，以「技能覆盖率」为主，
       岗位名方向为辅，加权得分。技能是最能反映胜任要求的信号。
    2. 技能清单缺失（JD 尚未补全）时退化为纯岗位名方向判断，并在理由中
       说明依据有限，避免用一个看似精确的分数误导用户。

    注意不要回到"命中数 ÷ requirements 长度"的老算法：requirements 是平台
    原始技术栈，条目越详细分母越大，会让好岗位得分反而更低。
    """
    title = str(job.get("title") or "").strip()
    target = (target_job or "").strip()
    requirements = [str(item).strip() for item in (job.get("requirements") or []) if str(item).strip()]

    if not title or not target:
        return {"score": 50, "matched_keywords": [], "level": "yellow", "missing": [], "reasons": "匹配度未知"}

    synonyms = next((v for k, v in KW_MAP.items() if k.lower() in target_job.lower()), [])
    direction, direction_reason = _direction_score(target, title, synonyms)

    if requirements and synonyms:
        # 技能覆盖率：目标岗位的核心技能中，有多少被这个岗位要求命中。
        hits = [
            skill for skill in synonyms
            if any(skill.lower() in req.lower() or req.lower() in skill.lower() for req in requirements)
        ]
        coverage = round(len(hits) / len(synonyms) * 100)
        # 取"方向"与"技能加成后"的较高者。
        #
        # 不能简单用覆盖率加权：JD 写得简略（只列 3 个技能）不代表岗位不对口，
        # 那样会让"Java开发工程师"这种完全对口的岗位因为技能少而被判成低匹配。
        # 因此以方向分为基线，技能命中只做上浮，命中越多上浮越大。
        skill_bonus = min(len(hits) * 8, 25) if hits else 0
        score = max(direction, round(coverage * 0.7 + direction * 0.3)) + skill_bonus
        score = min(score, 100)
        matched = hits
        missing = [skill for skill in synonyms if skill not in hits][:3]
        if hits:
            reasons = f"{direction_reason}；岗位要求覆盖你的「{'、'.join(hits[:3])}」等技能"
        else:
            reasons = f"{direction_reason}；岗位要求与你的核心技能重合较少"
    else:
        # JD 未补全：只能按方向判断，分数适度收敛避免过度自信。
        score = round(direction * 0.85)
        matched = []
        missing = []
        reasons = f"{direction_reason}（岗位详情尚未补全，匹配度依据有限）"

    if score >= 80:
        level = "green"
    elif score >= 55:
        level = "yellow"
    else:
        level = "red"

    return {
        "score": max(0, min(100, score)),
        "matched_keywords": matched,
        "level": level,
        "missing": missing,
        "reasons": reasons,
    }


@router.post("/jobs/search")
async def job_search(req: JobSearchRequest, current_user: User = Depends(get_current_user), db: DBSession = Depends(get_db)):
    """搜索真实职位。库为空时按当前关键词触发一次实时抓取，不返回 mock 职位。"""
    keyword = req.keyword or req.target_job or ""

    selected_locations = [value.strip() for value in req.locations if value.strip()]
    if req.provinces and not selected_locations:
        selected_locations = cities_for_provinces(req.provinces)

    # 优先从数据库读取
    db_jobs = _db_job_search(
        keyword=keyword,
        locations=selected_locations,
        educations=req.educations,
        db=db,
    )

    if db_jobs:
        # 用真实数据做匹配分级
        matched = []
        for job in db_jobs:
            m = _calc_match(req.target_job or keyword, job)
            matched.append({
                **job,
                "matchScore": m["score"],
                "matchLevel": m["level"],
                "reasons": m["reasons"],
                "missingSkills": m["missing"],
            })
        matched.sort(key=lambda x: x["matchScore"], reverse=True)
        return {"jobs": matched, "total": len(matched), "source": "db"}

    filters_active = bool(req.provinces or req.locations or req.educations)
    # 省份条件可能覆盖数十个城市，只在用户明确选到市时触发实时抓取。
    should_crawl = bool(keyword) and not (req.provinces and not req.locations)
    if should_crawl:
        try:
            await asyncio.wait_for(
                crawl_keyword(keyword, cities=req.locations or None),
                timeout=settings.CRAWLER_REQUEST_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            return {"jobs": [], "total": 0, "source": "live_unavailable", "message": "实时职位抓取超时，请稍后重试"}
        except Exception:
            return {"jobs": [], "total": 0, "source": "live_unavailable", "message": "实时职位暂时不可用，请稍后重试"}

        # 抓取器使用独立 DB 会话写入；结束本请求旧的读事务，避免 MySQL
        # REPEATABLE READ 快照看不到刚提交的职位。
        db.rollback()
        db_jobs = _db_job_search(
            keyword=keyword,
            locations=selected_locations,
            educations=req.educations,
            db=db,
        )
        if db_jobs:
            matched = []
            for job in db_jobs:
                m = _calc_match(req.target_job or keyword, job)
                matched.append({
                    **job,
                    "matchScore": m["score"],
                    "matchLevel": m["level"],
                    "reasons": m["reasons"],
                    "missingSkills": m["missing"],
                })
            matched.sort(key=lambda x: x["matchScore"], reverse=True)
            return {"jobs": matched, "total": len(matched), "source": "live"}

    message = (
        "当前筛选条件下暂无匹配职位，请调整筛选条件后重试"
        if filters_active
        else "暂无匹配的真实职位，请更换关键词后重试"
    )
    return {"jobs": [], "total": 0, "source": "empty", "message": message}


@router.get("/jobs/detail/{job_id}")
async def job_detail(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """返回岗位基础信息。

    岗位描述不再站内展示（前端只显示公司/地点/薪资/匹配度 + 原站链接），
    因此这里不再触发平台实时抓取：那条链路要打开浏览器、等待 20 秒以上，
    对一个不展示的字段并不值得。用户需要完整 JD 时点 url 去原站看。
    """
    row = db.query(Job).filter(Job.id == job_id, Job.is_active == True).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="职位不存在或已失效")

    return {"job": _job_payload(row, include_description=False), "detailSource": "summary"}


@router.post("/jobs/adapt")
async def adapt_resume(req: JobAdaptRequest, current_user: User = Depends(get_current_user)):
    """为指定岗位适配简历。"""
    return mock_adapt_resume(job_id=req.job_id, target_job=req.target_job)


@router.post("/jobs/apply")
async def apply_job(
    req: JobApplyRequest,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """一键投递 —— 持久化到 applications 表。"""
    # 尝试从 DB 查找职位信息
    job_title = ""
    company = ""
    if req.job_id.startswith("job_db_"):
        try:
            db_job_id = int(req.job_id.replace("job_db_", ""))
        except ValueError:
            db_job_id = None
        if db_job_id is not None:
            job_row = db.query(Job).filter(Job.id == db_job_id).first()
            if job_row:
                job_title = job_row.title
                company = job_row.company

    if not job_title:
        # fallback mock
        mock_result = mock_apply_job(job_id=req.job_id, resume_version=req.resume_version)
        job_title = mock_result.get("jobTitle", "")
        company = mock_result.get("company", "")

    now = datetime.datetime.now(datetime.timezone.utc)
    app_id = f"app_{uuid.uuid4().hex[:12]}"

    application = Application(
        id=app_id,
        user_id=current_user.id,
        job_id=req.job_id,
        job_title=job_title or "未知职位",
        company=company or "未知公司",
        resume_version=req.resume_version or "original",
        status="applied",
        status_label="已投递",
        status_history=[{"status": "applied", "at": now.isoformat(), "label": "简历已投递"}],
        applied_at=now,
    )
    db.add(application)
    db.commit()
    db.refresh(application)

    return {
        "applicationId": application.id,
        "jobId": application.job_id,
        "jobTitle": application.job_title,
        "company": application.company,
        "resumeVersion": application.resume_version,
        "appliedAt": application.applied_at.isoformat() if application.applied_at else "",
        "status": application.status,
        "statusLabel": application.status_label,
        "statusHistory": application.status_history or [],
    }


@router.get("/jobs/applications")
async def get_applications(
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """获取当前用户所有投递记录和统计（从 DB 读取）。"""
    rows = (
        db.query(Application)
        .filter(Application.user_id == current_user.id)
        .order_by(Application.applied_at.desc(), Application.id.desc())
        .all()
    )

    if not rows:
        return {"applications": [], "stats": {
            "total": 0, "screened": 0, "interviewing": 0, "offered": 0, "rejected": 0,
        }}

    applications = []
    for row in rows:
        applications.append({
            "id": row.id,
            "jobId": row.job_id,
            "jobTitle": row.job_title,
            "company": row.company,
            "resumeVersion": row.resume_version,
            "appliedAt": row.applied_at.isoformat() if row.applied_at else "",
            "status": row.status,
            "statusLabel": row.status_label,
            "statusHistory": row.status_history or [],
        })

    total = len(applications)
    stats = {
        "total": total,
        "screened": sum(1 for a in applications if a["status"] in ("screened", "interviewing", "offered", "rejected")),
        "interviewing": sum(1 for a in applications if a["status"] in ("interviewing", "offered")),
        "offered": sum(1 for a in applications if a["status"] == "offered"),
        "rejected": sum(1 for a in applications if a["status"] == "rejected"),
    }

    return {"applications": applications, "stats": stats}


@router.post("/jobs/applications/status")
async def update_application_status(
    req: ApplicationStatusRequest,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """更新投递状态 —— 持久化到 DB。"""
    application = (
        db.query(Application)
        .filter(Application.id == req.application_id, Application.user_id == current_user.id)
        .first()
    )
    if application is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="投递记录不存在")

    if req.status not in STATUS_LABEL_MAP:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="投递状态不合法")

    now = datetime.datetime.now(datetime.timezone.utc)
    label = STATUS_LABEL_MAP[req.status]

    history = list(application.status_history or [])
    history.append({"status": req.status, "at": now.isoformat(), "label": label})

    application.status = req.status
    application.status_label = label
    application.status_history = history
    application.updated_at = now
    db.commit()

    return {
        "applicationId": application.id,
        "status": application.status,
        "statusLabel": application.status_label,
        "updatedAt": now.isoformat(),
    }
