"""
岗位需求画像 —— 从真实抓取的 JD 反推"这个岗位到底要什么"

这是评分体系里唯一的"岗位标准"来源。在此之前,岗位要求是两份手写常量:
- `mock/fallback.py::KW_MAP` —— 9 个岗位的固定技能清单
- `scoring_rules.py::JOB_LEXICON` —— 一份拍脑袋的岗位词表

问题不在于它们写得对不对,而在于它们是**想当然**的:爬虫抓 30 类岗位,
KW_MAP 只覆盖 9 类;市场上 Java 岗位早已普遍要求 K8s,词表里却没有。
岗位需求每年都在变,手写常量注定过期。

现在改为:按目标岗位检索 jobs 表里的真实 JD,统计技能的**文档频率**
(出现在多少条 JD 里),频率就是权重。10 条 JD 里 9 条要 MySQL、
1 条要 Flink,那 MySQL 就该比 Flink 重要 9 倍 —— 这个结论来自市场,
不来自我们的臆断。

语料为空时(新部署、爬虫挂了)降级到 STARTER_PROFILES,并在返回值里
标注 source,让调用方能如实告知用户依据的是什么。
"""
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from sqlalchemy import or_
from sqlalchemy.orm import Session as DBSession

from app.core.database import SessionLocal
from app.models.db_models import Job
from app.services.skill_extract import canonicalize, extract_skills

logger = logging.getLogger("glint.jd_corpus")

# 一个岗位画像至少要有这么多条 JD 才算可信,否则降级。
# 3 条以下的统计量没有意义,单条 JD 的个性化要求会被当成行业标准。
MIN_CORPUS_SIZE = 3

# 画像缓存时长。JD 抓取是 2 小时一轮,缓存 30 分钟既不会读到太旧的数据,
# 又能避免每次搜索都全表扫描。
CACHE_TTL_SECONDS = 30 * 60

# 降级画像(starter/empty)的缓存时长要短得多。
# 冷启动或爬虫刚失败时会缓存一份兜底画像,如果沿用 30 分钟,
# 爬虫补完数据后用户还要继续看半小时的"通用岗位模型"评分。
# 1 分钟足以挡住高频重复查询,又能在数据到位后很快切回真实语料。
DEGRADED_CACHE_TTL_SECONDS = 60

# 单个岗位最多取多少条 JD 参与统计。超过这个量对权重分布没有实质影响,
# 只是徒增查询开销。
MAX_CORPUS_SIZE = 200

# 缓存条目上限。target_job 由用户输入,不设上限的话每个不同岗位名
# 都会永久占一个槽位。超限时按写入时间淘汰最旧的一批。
MAX_CACHE_ENTRIES = 512


# ============ 降级用的兜底画像 ============

# 仅在 jobs 表为空时使用。刻意只保留最粗的几类 + 明确标注为兜底,
# 避免它再次演变成"事实上的岗位标准"。
STARTER_PROFILES: Dict[str, List[str]] = {
    "后端": ["Java", "Python", "MySQL", "Redis", "SQL", "Linux", "Git", "微服务"],
    "前端": ["JavaScript", "Vue", "React", "CSS", "HTML", "TypeScript", "Webpack"],
    "算法": ["Python", "机器学习", "深度学习", "PyTorch", "SQL", "特征工程"],
    "数据": ["SQL", "Python", "数据分析", "数据可视化", "统计分析", "Excel"],
    "测试": ["自动化测试", "接口测试", "测试用例", "Python", "Linux", "性能测试"],
    "产品": ["需求分析", "PRD", "原型设计", "竞品分析", "数据分析", "用户研究"],
    "运营": ["内容运营", "用户运营", "活动策划", "数据分析", "新媒体运营"],
    "设计": ["UI设计", "交互设计", "Figma", "原型设计", "用户体验"],
    "运维": ["Linux", "Docker", "Kubernetes", "Shell", "Nginx", "CI/CD"],
}

# 岗位名 -> 兜底画像 key 的粗分类线索
_STARTER_HINTS: List[Tuple[Tuple[str, ...], str]] = [
    (("后端", "服务端", "java", "python开发", "go", "golang", "php", "c++"), "后端"),
    (("前端", "web", "vue", "react", "h5", "小程序"), "前端"),
    (("算法", "机器学习", "深度学习", "ai", "人工智能", "大模型", "nlp", "视觉"), "算法"),
    (("数据分析", "数据", "bi", "数仓", "大数据"), "数据"),
    (("测试", "qa", "质量"), "测试"),
    (("产品",), "产品"),
    (("运营", "市场", "增长"), "运营"),
    (("设计", "ui", "ux", "交互", "视觉"), "设计"),
    (("运维", "sre", "devops"), "运维"),
]


@dataclass
class JobProfile:
    """一个目标岗位的需求画像"""

    target_job: str
    # 规范技能名 -> 权重(0~1),权重即该技能在语料中的文档频率
    skill_weights: Dict[str, float] = field(default_factory=dict)
    # 参与统计的 JD 条数
    sample_size: int = 0
    # "jd" = 来自真实语料; "starter" = 语料不足时的兜底; "empty" = 无岗位信息
    source: str = "empty"

    @property
    def is_empirical(self) -> bool:
        """画像是否来自真实市场数据"""
        return self.source == "jd"

    def weight_of(self, skill: str) -> float:
        return self.skill_weights.get(skill, 0.0)

    def neutral_weight(self) -> float:
        """
        画像里没有的技能该记多少权重。

        不能固定给 0.5 —— 画像权重是文档频率,含义是"多少比例的 JD 要求它",
        实际分布常集中在 0.6~1.0。固定 0.5 会让"整个市场都没提过的冷门技能"
        比一半的真实要求还重要,缺它反而扣得更多。
        改取画像权重的中位数并再打 8 折:它确实是这条 JD 的要求(不能记 0),
        但既然市场语料里没出现过,重要性理应低于该岗位的典型要求。
        """
        if not self.skill_weights:
            return 0.5
        values = sorted(self.skill_weights.values())
        median = values[len(values) // 2]
        return max(0.05, median * 0.8)


# 进程内缓存: target_job(小写) -> (画像, 写入时间)
_CACHE: Dict[str, Tuple[JobProfile, float]] = {}


def _now() -> float:
    return time.monotonic()


def clear_cache() -> None:
    """清空画像缓存。

    缓存是**进程内**的,因此只能由本进程调用才有效
    (另起一个 python 进程调用它清的是那个进程自己的空字典)。
    主要给测试隔离用例状态用;运行中的服务无需手动清理 ——
    降级画像 1 分钟后自动重建,真实画像 30 分钟后自动过期。
    """
    _CACHE.clear()


def _starter_key(target_job: str) -> Optional[str]:
    low = target_job.lower()
    for hints, key in _STARTER_HINTS:
        if any(h in low for h in hints):
            return key
    return None


def _starter_profile(target_job: str) -> JobProfile:
    """语料不足时的兜底画像。权重按顺序线性递减,表达"越靠前越核心"。"""
    key = _starter_key(target_job)
    if key is None:
        return JobProfile(target_job=target_job, source="empty")
    skills = STARTER_PROFILES[key]
    n = len(skills)
    # 权重从 1.0 递减到 0.5,保持相对次序但不假装有精确的市场频率
    weights = {s: 1.0 - 0.5 * (i / max(1, n - 1)) for i, s in enumerate(skills)}
    return JobProfile(
        target_job=target_job, skill_weights=weights, sample_size=0, source="starter"
    )


def _job_search_terms(target_job: str) -> List[str]:
    """
    把目标岗位名拆成用于检索 JD 的词。

    "Java后端开发工程师" 要能召回标题含 "Java" 或 "后端" 的 JD。
    直接用整串 LIKE 匹配几乎召回不到东西 —— 这正是旧匹配度恒定的根因之一。

    单字符词一律丢弃:"的""A" 这类词 LIKE '%的%' 会命中几乎所有 JD,
    把无关岗位混进语料,统计出来的"岗位要求"就失真了。
    """
    if not target_job:
        return []
    terms: List[str] = []
    # 英文/数字片段(Java、C++、UI)
    for m in re.finditer(r"[A-Za-z][A-Za-z0-9+#.]*", target_job):
        token = m.group(0)
        if len(token) >= 2:
            terms.append(token)
    # 中文片段:去掉无区分度的通用后缀后,保留 2~4 字的核心词
    zh = re.sub(r"[A-Za-z0-9+#.\s]+", "", target_job)
    zh = re.sub(r"(工程师|实习生|专员|助理|岗位|岗|开发|研发)", "", zh)
    if len(zh) >= 2:
        terms.append(zh[:4])
        # 附加前两字,提高召回("数据分析" -> 也检索 "数据")
        if len(zh) > 2:
            terms.append(zh[:2])
    # 整串也作为一个检索词,精确匹配的 JD 相关性最高
    whole = target_job.strip()
    if len(whole) >= 2:
        terms.insert(0, whole)
    # 去重保序,并剔除过短的词
    seen = set()
    return [
        t for t in terms
        if len(t) >= 2 and not (t.lower() in seen or seen.add(t.lower()))
    ]


def _like_pattern(term: str) -> str:
    """
    构造 LIKE 模式,转义用户可控的通配符。

    target_job 来自用户输入,若原样拼进 LIKE,"%" 会变成"匹配任意内容",
    "_" 会变成"匹配任意单字符" —— 前者让检索退化为全表扫描,
    后者让召回结果不可预期。参数本身仍由 SQLAlchemy 绑定,不存在注入,
    但通配符语义必须显式转义掉。
    """
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _fetch_jd_rows(db: DBSession, target_job: str) -> List[Job]:
    """按岗位名检索相关 JD。优先标题命中,不足时放宽到描述。"""
    terms = _job_search_terms(target_job)
    if not terms:
        return []

    title_filters = [Job.title.like(_like_pattern(t), escape="\\") for t in terms]
    rows = (
        db.query(Job)
        .filter(Job.is_active == True, or_(*title_filters))
        .order_by(Job.crawled_at.desc())
        .limit(MAX_CORPUS_SIZE)
        .all()
    )
    if len(rows) >= MIN_CORPUS_SIZE:
        return rows

    # 标题召回不足,放宽到描述。相关性略低,但总好过没有数据。
    broad_filters = [Job.description.like(_like_pattern(t), escape="\\") for t in terms]
    extra = (
        db.query(Job)
        .filter(Job.is_active == True, or_(*broad_filters))
        .order_by(Job.crawled_at.desc())
        .limit(MAX_CORPUS_SIZE)
        .all()
    )
    merged = {r.id: r for r in rows}
    for r in extra:
        merged.setdefault(r.id, r)
    return list(merged.values())


def _skills_of_job(row: Job) -> List[str]:
    """
    从一条 JD 里取出它要求的技能。

    三个来源合并:结构化的 requirements、平台标签 tags、以及描述正文。
    requirements 是爬虫抽好的,tags 是平台自带的,描述兜底 —— 早期入库的
    数据 requirements 可能为空,不看描述就会白白丢掉一条语料。

    tags 必须 strict 归一:各平台该字段语义不一(智联放福利、猎聘放公司标签),
    原样计入会让"五险一金"成为高频"技能要求",直接污染岗位画像。
    """
    skills = canonicalize(
        list(row.requirements or []) + list(row.tags or []), strict=True
    )
    if row.description:
        for s in extract_skills(row.description):
            if s not in skills:
                skills.append(s)
    return skills


def build_profile(db: Optional[DBSession], target_job: str) -> JobProfile:
    """
    构建目标岗位的需求画像。带进程内缓存。

    db 为 None 时自建一个只读会话去查语料 —— 评分接口(resume/evaluate)
    没有现成的 db 依赖,但同样应该按真实 JD 标准来评分,不能因为调用方
    没传 session 就退化成兜底词表。取不到语料时静默降级,不影响主流程。

    降级画像只缓存 1 分钟(见 DEGRADED_CACHE_TTL_SECONDS):否则爬虫补完
    数据后,用户还要再看半小时基于兜底模型算出来的分数。
    """
    job = (target_job or "").strip()
    if not job:
        return JobProfile(target_job="", source="empty")

    cache_key = job.lower()
    cached = _CACHE.get(cache_key)
    if cached:
        profile, written_at = cached
        ttl = (CACHE_TTL_SECONDS if profile.is_empirical
               else DEGRADED_CACHE_TTL_SECONDS)
        if _now() - written_at < ttl:
            return profile

    profile = _starter_profile(job)
    own_session = None
    try:
        if db is None:
            own_session = SessionLocal()
            db = own_session
        rows = _fetch_jd_rows(db, job)
        if len(rows) >= MIN_CORPUS_SIZE:
            counter: Dict[str, int] = {}
            for row in rows:
                # 同一条 JD 里重复出现的技能只算一次 —— 统计的是
                # "多少条 JD 要求它",不是"被提及多少次"
                for skill in set(_skills_of_job(row)):
                    counter[skill] = counter.get(skill, 0) + 1
            if counter:
                total = len(rows)
                profile = JobProfile(
                    target_job=job,
                    skill_weights={s: c / total for s, c in counter.items()},
                    sample_size=total,
                    source="jd",
                )
    except Exception as exc:
        # 语料构建失败不能影响主流程,降级即可
        logger.warning(
            "jd_profile_build_failed",
            extra={"target_job": job, "error": str(exc)},
        )
    finally:
        if own_session is not None:
            own_session.close()

    _remember(cache_key, profile)
    return profile


def _remember(cache_key: str, profile: JobProfile) -> None:
    """写入缓存,并在超出上限时淘汰最旧的条目。"""
    if len(_CACHE) >= MAX_CACHE_ENTRIES:
        # 一次清掉最旧的 1/4,避免每次写入都要排序
        drop = sorted(_CACHE.items(), key=lambda kv: kv[1][1])[: MAX_CACHE_ENTRIES // 4]
        for key, _ in drop:
            _CACHE.pop(key, None)
    _CACHE[cache_key] = (profile, _now())
