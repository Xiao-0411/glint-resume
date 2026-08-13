"""
技能识别 —— 全站唯一的"从文本里认出技能词"实现

在此之前有三份几乎相同的 `_extract_requirements` 分散在
zhipin/zhaopin/liepin 里,各自用裸正则 `re.search("SQL", desc)` 匹配,
导致 "PostgreSQL" 命中 SQL、"Golang" 命中 Go。技能词一旦抽错,
下游的岗位匹配度和简历匹配度就全是错的。

这里解决两件事:
1. **别名归一** —— "k8s"/"Kubernetes"、"js"/"JavaScript" 归到同一个规范名,
   否则简历写 k8s、JD 写 Kubernetes 就匹配不上。
2. **边界安全** —— 英文技能词要求前后不是字母数字,中文词直接子串匹配
   (中文没有词边界概念)。
"""
import re
from typing import Dict, Iterable, List, Set

# 规范名 -> 别名。别名不含规范名自身,匹配时会自动带上。
# 只收录在招聘 JD 和学生简历里真实高频出现的词,不求穷尽。
SKILL_ALIASES: Dict[str, List[str]] = {
    # ---- 编程语言 ----
    "Java": ["Java"],
    "Python": ["Python"],
    "Go": ["Go", "Golang", "Go语言"],
    "C++": ["C++"],
    "C#": ["C#"],
    "C": ["C语言"],
    "JavaScript": ["JavaScript", "JS", "ES6"],
    "TypeScript": ["TypeScript", "TS"],
    "Rust": ["Rust"],
    "Kotlin": ["Kotlin"],
    "Swift": ["Swift"],
    "PHP": ["PHP"],
    "Scala": ["Scala"],
    "Shell": ["Shell", "Bash"],
    # ---- 后端框架/中间件 ----
    "Spring": ["Spring", "SpringBoot", "Spring Boot", "Spring Cloud", "SpringMVC"],
    "Django": ["Django"],
    "Flask": ["Flask"],
    "FastAPI": ["FastAPI"],
    "Node.js": ["Node.js", "NodeJS", "Node"],
    "MyBatis": ["MyBatis"],
    "Netty": ["Netty"],
    "gRPC": ["gRPC"],
    "RabbitMQ": ["RabbitMQ"],
    "Kafka": ["Kafka"],
    "Dubbo": ["Dubbo"],
    "微服务": ["微服务"],
    # ---- 前端 ----
    "Vue": ["Vue", "Vue.js", "Vue3"],
    "React": ["React", "React.js"],
    "Angular": ["Angular"],
    "HTML": ["HTML", "HTML5"],
    "CSS": ["CSS", "CSS3", "Sass", "Less"],
    "Webpack": ["Webpack", "Vite"],
    "小程序": ["小程序"],
    "响应式布局": ["响应式布局", "响应式设计"],
    # ---- 数据库/存储 ----
    "MySQL": ["MySQL"],
    "PostgreSQL": ["PostgreSQL", "Postgres"],
    "MongoDB": ["MongoDB"],
    "Redis": ["Redis"],
    "Elasticsearch": ["Elasticsearch", "ES搜索"],
    "SQL": ["SQL"],
    "Oracle": ["Oracle"],
    "HBase": ["HBase"],
    # ---- 运维/云 ----
    "Docker": ["Docker"],
    "Kubernetes": ["Kubernetes", "K8s"],
    "Linux": ["Linux"],
    "Git": ["Git"],
    "CI/CD": ["CI/CD", "Jenkins", "GitLab CI"],
    "Nginx": ["Nginx"],
    "AWS": ["AWS"],
    "阿里云": ["阿里云"],
    "腾讯云": ["腾讯云"],
    # ---- 数据/算法 ----
    "机器学习": ["机器学习", "MachineLearning"],
    "深度学习": ["深度学习", "DeepLearning"],
    "NLP": ["NLP", "自然语言处理"],
    "CV": ["计算机视觉", "图像识别"],
    "大模型": ["大模型", "LLM", "AIGC", "Prompt工程"],
    "PyTorch": ["PyTorch"],
    "TensorFlow": ["TensorFlow"],
    "Spark": ["Spark"],
    "Hadoop": ["Hadoop"],
    "Flink": ["Flink"],
    "数据分析": ["数据分析", "数据统计"],
    "数据可视化": ["数据可视化", "BI", "Tableau", "PowerBI"],
    "数据挖掘": ["数据挖掘"],
    "统计分析": ["统计分析", "统计学"],
    "推荐系统": ["推荐系统", "推荐算法"],
    "特征工程": ["特征工程"],
    # ---- 测试 ----
    "自动化测试": ["自动化测试", "Selenium", "Appium"],
    "性能测试": ["性能测试", "JMeter", "LoadRunner"],
    "测试用例": ["测试用例", "用例设计"],
    "接口测试": ["接口测试", "Postman"],
    # ---- 产品/设计 ----
    "需求分析": ["需求分析", "需求调研"],
    "产品设计": ["产品设计", "产品规划"],
    "PRD": ["PRD", "需求文档"],
    "原型设计": ["原型设计", "Axure", "墨刀"],
    "Figma": ["Figma"],
    "Sketch": ["Sketch"],
    "用户研究": ["用户研究", "用户调研", "用户访谈"],
    "交互设计": ["交互设计"],
    "UI设计": ["UI设计", "视觉设计"],
    "竞品分析": ["竞品分析"],
    "用户体验": ["用户体验", "UX"],
    # ---- 运营/市场 ----
    "内容运营": ["内容运营", "文案撰写", "文案策划"],
    "用户运营": ["用户运营", "社群运营"],
    "活动策划": ["活动策划", "活动运营"],
    "新媒体运营": ["新媒体运营", "公众号运营", "短视频运营"],
    "电商运营": ["电商运营", "店铺运营"],
    "数据复盘": ["数据复盘", "复盘分析"],
    "市场调研": ["市场调研"],
    "SEO": ["SEO", "SEM"],
    # ---- 通用职场 ----
    "项目管理": ["项目管理", "敏捷开发", "Scrum"],
    "Excel": ["Excel", "表格处理"],
    "PPT": ["PPT", "演示文稿"],
    "团队协作": ["团队协作", "跨部门协作"],
    "沟通能力": ["沟通能力", "沟通协调"],
}

# 别名 -> 规范名。别名越长越先匹配,避免 "Spring Boot" 被 "Spring" 抢先吃掉。
_ALIAS_TO_CANON: Dict[str, str] = {}
for _canon, _aliases in SKILL_ALIASES.items():
    for _alias in _aliases:
        _ALIAS_TO_CANON[_alias.lower()] = _canon
_SORTED_ALIASES = sorted(_ALIAS_TO_CANON, key=len, reverse=True)


def _compile(alias: str) -> re.Pattern:
    """
    英文/数字开头结尾的别名要加边界,中文别名不加。

    Python 的 \\b 在 "SQL" 与 "PostgreSQL" 之间不起作用(L 和 S 都是词字符时
    \\bSQL 确实能挡住,但 "C++" 这类含正则元字符的词 \\b 会失效),
    所以统一用 lookaround 显式声明"前后不能是字母数字"。
    中文词跳过边界检查 —— 中文不分词,加了反而匹配不到。
    """
    escaped = re.escape(alias)
    prefix = r"(?<![A-Za-z0-9])" if alias[0].isascii() and alias[0].isalnum() else ""
    suffix = r"(?![A-Za-z0-9])" if alias[-1].isascii() and alias[-1].isalnum() else ""
    return re.compile(prefix + escaped + suffix, re.IGNORECASE)


_ALIAS_PATTERNS = [(alias, _compile(alias)) for alias in _SORTED_ALIASES]


def extract_skills(text: str, limit: int = 0) -> List[str]:
    """
    从任意文本(JD 描述 / 简历正文)中抽出规范化技能名,按词表顺序去重。

    limit > 0 时截断,用于爬虫侧控制存储量。
    """
    if not text:
        return []
    found: List[str] = []
    seen: Set[str] = set()
    for alias, pattern in _ALIAS_PATTERNS:
        canon = _ALIAS_TO_CANON[alias]
        if canon in seen:
            continue
        if pattern.search(text):
            seen.add(canon)
            found.append(canon)
            if limit and len(found) >= limit:
                break
    return found


def canonicalize(items: Iterable[str]) -> List[str]:
    """
    把已经是"技能条目"的列表(简历 skills、JD tags)归一到规范名。

    与 extract_skills 的区别:这里每个条目本身就是技能词,
    因此整条命中即可;命中不了的原样保留(用户可能写了词表外的技能)。
    """
    out: List[str] = []
    seen: Set[str] = set()
    for raw in items or []:
        if not isinstance(raw, str) or not raw.strip():
            continue
        item = raw.strip()
        canon = _ALIAS_TO_CANON.get(item.lower())
        if canon is None:
            hits = extract_skills(item, limit=1)
            canon = hits[0] if hits else item
        if canon not in seen:
            seen.add(canon)
            out.append(canon)
    return out
