"""
评分规则库 —— 五维评分的纯函数实现

与 evaluation_service 分离的原因:这里全是无副作用的纯函数,
可以脱离 LLM 和数据库单独测试,也方便后续调权重时对照基准用例。

设计原则:
1. 零分锚定 —— 空简历各维度接近 0,不给保底分。分数区间必须能拉开差距。
2. 证据累积 —— 分数来自"发现了多少可佐证的内容",而非"扣了多少分"。
3. 双向计分 —— 好的加分,差的扣分;可信度尤其要能加分,否则经历越多越吃亏。
"""
import re
from typing import Dict, List, Tuple


# ============ 量化识别 ============

# 真正的量化 = 数字 + 量纲。单位不再可选,避免 "Python3" "第2组" 这类误判。
_UNIT = (
    r"%|‰|万|千|百|亿|个|条|人|次|篇|位|倍|分|名|页|款|家|门|届|起|件|单|张|台|套|"
    r"ms|s|秒|分钟|小时|天|周|月|年|"
    r"KB|MB|GB|TB|k|K|w|W|"
    r"元|万元|美元|人民币|"
    r"倍|pt|px|fps|QPS|qps|TPS|tps"
)
# 数字。写成 \d+(?:\.\d+)? 而不是 \d+\.?\d* —— 后者两个量词能互相分配
# 同一串数字,匹配失败时会指数级回溯(200 位连续数字实测单次 220ms,
# 是可被简历正文触发的 ReDoS)。要求小数点后必须有数字即可消除歧义,
# 识别能力不变("3.5%""42个"照常命中)。
_NUM = r"\d+(?:\.\d+)?"

QUANT_WITH_UNIT = re.compile(rf"{_NUM}\s*(?:{_UNIT})", re.IGNORECASE)

# 成果型量化:提升/降低/减少 …… 数字,这类表述价值最高。
#
# 这里的分隔符要同时挡住两类误判,曾经两边都踩过坑:
# 1. 标点断句 —— "显著提升，覆盖3个模块" 不是成果量化(前后是两件事)。
# 2. 空格断句 —— "提升 团队协作 参与3次评审" 同理。
# 但空格又不能一律当断句:"耗时降低 65%" 是比 "耗时降低65%" 更规范的排版,
# 若把空格算作分隔,加个空格量化度就从 100 掉到 52。
#
# 折中:动词与数字之间允许出现空格,但**最多一段连续空白**,
# 且中间不能夹杂其他词。用 \s{0,2} 精确表达"紧邻",而不是笼统地
# 允许任意 12 个非标点字符。
_SEP = r",，。.;；、!！?？"
_DELTA_VERB = r"提升|提高|增长|增加|降低|减少|缩短|压缩|下降|优化|节省|加快|翻"
# 动词与数字之间只允许:少量非空白连接字(了/至/到/约/近/达 等)+ 紧邻空格
_GAP = rf"[^{_SEP}\s]{{0,8}}?\s{{0,2}}"
QUANT_DELTA = re.compile(
    rf"(?:{_DELTA_VERB}){_GAP}{_NUM}\s*(?:{_UNIT})", re.IGNORECASE
)
# 反向语序:"数字% 的提升"
QUANT_DELTA_REV = re.compile(
    rf"{_NUM}\s*(?:{_UNIT})\s{{0,2}}[^{_SEP}\s]{{0,6}}?(?:{_DELTA_VERB})", re.IGNORECASE
)

# 排名型:前 10%、第 2 名、Top 3。
# 排名单位是必需的 —— 否则 "第2组组长" 这种编号会被误判为量化成果。
QUANT_RANK = re.compile(rf"(?:前|第)\s*{_NUM}\s*(?:%|名|位|强)|top\s*\d+", re.IGNORECASE)

# 前后对比型:"从 800ms 优化至 120ms"、"从2000万降至200万"、"QPS 从 200 提升到 1200"。
# 这是简历里最有说服力的写法之一,但两端数字未必都带量纲
# (如 "QPS 从 200 提升至 1200",QPS 写在前面而不是作为单位跟在数字后),
# 上面的 QUANT_DELTA 会漏掉。这里单独识别"从 A 到 B"结构。
#
# 必须排除时间区间 —— "从2019年到2021年" 是任职时间,不是成果。
# 因此:带"年/月/日/届"等时间单位的区间不计入,且连接词只认变化类动词,
# 光靠"到/至"不够(从北京到上海也是"到")。
_TIME_UNIT = r"年|月|日|届|周|天|季度|学期"
QUANT_RANGE = re.compile(
    # "从" 后可跟少量限定语("每月""日均"),再到数字
    rf"从\s*[^{_SEP}\d]{{0,3}}?\s*{_NUM}\s*(?!(?:{_TIME_UNIT}))(?:{_UNIT})?[^{_SEP}]{{0,6}}?"
    rf"(?:降至|降到|升至|升到|增至|增到|减至|减到|优化至|优化到|提升至|提升到|"
    rf"下降至|下降到|缩短至|缩短到|降|升|增|减)\s*"
    rf"{_NUM}\s*(?!(?:{_TIME_UNIT}))",
    re.IGNORECASE,
)

# 模糊词 —— 出现即扣分,因为它们正是"假量化"的信号
VAGUE_WORDS = (
    "显著", "大幅", "极大", "较多", "较快", "较好", "很多", "不少", "许多",
    "明显", "有效地", "大量", "海量", "众多", "若干", "一定程度", "相当",
    "非常好", "很好", "不错", "优异", "出色", "丰富的经验",
)


# ============ 动词分级 ============

# 强动词:体现主导性和设计能力
VERB_STRONG = {
    "主导", "设计", "架构", "构建", "搭建", "重构", "定义", "规划", "创建",
    "孵化", "从0到1", "牵头", "统筹", "主持", "独立完成", "自主研发",
}
# 中性动词:体现执行力,是简历的主体
VERB_NEUTRAL = {
    "实现", "开发", "优化", "分析", "推动", "落地", "调研", "评估", "迭代",
    "提升", "降低", "整合", "协调", "支撑", "驱动", "运营", "策划", "复盘",
    "编写", "测试", "部署", "维护", "管理", "负责", "承担", "输出", "交付",
    "改进", "完善", "拓展", "沉淀", "梳理", "验证", "排查", "修复",
}
# 弱动词/口语:出现在开头要扣分
VERB_WEAK = {
    "做了", "搞了", "弄了", "帮忙", "帮助", "参加", "参与", "跟着", "协助",
    "学习", "了解", "熟悉", "接触", "尝试", "打杂", "打下手",
}

# 第一人称 —— 简历正文不该出现
FIRST_PERSON = ("我", "我们", "本人", "自己")

# 可验证性信号:出现说明内容可追溯
VERIFIABLE_SIGNALS = (
    "github", "gitee", "http://", "https://", "www.",
    "专利", "论文", "著作权", "证书", "编号", "已上线", "已发布",
    "开源", "线上", "生产环境", "用户量", "下载量", "star",
)

# 夸大词:可信度扣分
EXAGGERATION = (
    "完美", "史无前例", "行业领先", "国内首创", "世界一流", "顶尖",
    "唯一", "最强", "革命性", "颠覆", "无人能及", "碾压", "完胜",
)


# ============ 中文分词(轻量,无外部依赖) ============

# 常见岗位领域词,用于匹配度切分。不求全,只求覆盖主流校招岗位。
JOB_LEXICON = [
    # 技术方向
    "后端", "前端", "全栈", "客户端", "服务端", "移动端", "嵌入式",
    "算法", "机器学习", "深度学习", "人工智能", "大模型", "自然语言处理",
    "数据分析", "数据挖掘", "数据仓库", "大数据", "数据科学",
    "测试", "运维", "安全", "网络", "数据库", "中间件", "架构",
    "音视频", "图形学", "推荐系统", "搜索", "广告", "风控",
    # 语言/技术栈
    "java", "python", "golang", "go", "c++", "c#", "javascript", "typescript",
    "rust", "kotlin", "swift", "php", "ruby", "scala",
    "vue", "react", "angular", "node", "spring", "django", "flask",
    "mysql", "redis", "kafka", "docker", "kubernetes", "k8s", "linux",
    "pytorch", "tensorflow", "spark", "hadoop", "flink", "elasticsearch",
    # 职能方向
    "产品经理", "产品", "运营", "市场", "销售", "人力资源", "财务", "法务",
    "设计师", "设计", "交互", "视觉", "用户研究", "内容", "编辑",
    "项目管理", "咨询", "战略", "投研", "投资", "风险管理",
    # 通用后缀
    "工程师", "开发", "研发", "实习生", "专员", "助理", "顾问", "分析师",
]
# 长词优先,避免 "产品" 抢先吃掉 "产品经理"
JOB_LEXICON_SORTED = sorted(JOB_LEXICON, key=len, reverse=True)

# 这些词命中了也说明不了什么,不计入匹配度
STOPWORD_TOKENS = {"工程师", "实习生", "专员", "助理", "开发", "研发", "岗", "岗位"}


def tokenize_job(job: str) -> List[str]:
    """
    切分岗位名为关键词。
    原实现用 [\\s/、,,]+ 切分,中文岗位名没有分隔符,
    "Java后端开发工程师" 会整体变成一个 token,导致匹配度恒定。
    这里改为:词典最长匹配 + 英文单词 + 剩余中文 2-gram 兜底。
    """
    if not job:
        return []
    text = job.lower().strip()
    tokens: List[str] = []

    # 1. 词典最长匹配,命中后用空格占位,防止重复切分
    for word in JOB_LEXICON_SORTED:
        if word in text:
            tokens.append(word)
            text = text.replace(word, " ")

    # 2. 剩余的连续英文/数字当作独立 token
    for m in re.finditer(r"[a-z][a-z0-9+#.]{1,}", text):
        tokens.append(m.group(0))
    text = re.sub(r"[a-z][a-z0-9+#.]{1,}", " ", text)

    # 3. 剩余中文做 2-gram 兜底,保证生僻岗位名也能切出东西
    for chunk in re.split(r"[^一-龥]+", text):
        if len(chunk) >= 2:
            for i in range(len(chunk) - 1):
                tokens.append(chunk[i:i + 2])
        elif len(chunk) == 1:
            tokens.append(chunk)

    # 去重保序,并剔除无信息量的通用后缀
    seen = set()
    out = []
    for t in tokens:
        t = t.strip()
        if not t or t in seen or t in STOPWORD_TOKENS:
            continue
        seen.add(t)
        out.append(t)
    return out


def collect_bullets(resume: Dict) -> List[str]:
    """取出所有经历的 bullet 文本"""
    bullets: List[str] = []
    for exp in resume.get("experiences") or []:
        for b in exp.get("bullets") or []:
            if isinstance(b, str) and b.strip():
                bullets.append(b.strip())
    return bullets


# ============ 单条 bullet 的细粒度评估 ============

# 参与正则匹配的最大长度。真实 bullet 通常 25~80 字,超长的要么是用户
# 误粘贴了整段文本,要么是刻意构造的长串 —— 后者会让含可变量词的正则
# 产生大量回溯(实测 900 字的构造串单次匹配 600ms+)。截断到 200 字既
# 覆盖所有正常写法,又把最坏耗时压到微秒级。
MAX_SCAN_LEN = 200


def score_bullet_quant(bullet: str) -> float:
    """
    单条 bullet 的量化质量,0~1。
    成果型量化(提升 30% / 从 800ms 降到 120ms) > 普通量化(5 人) > 排名 > 无。
    模糊词扣分。
    """
    bullet = bullet[:MAX_SCAN_LEN]
    score = 0.0
    if (QUANT_DELTA.search(bullet) or QUANT_DELTA_REV.search(bullet)
            or QUANT_RANGE.search(bullet)):
        score = 1.0
    elif QUANT_WITH_UNIT.search(bullet):
        # 有量纲数字,但没体现变化量
        score = 0.65
        # 多个量化数据的更充分
        if len(QUANT_WITH_UNIT.findall(bullet)) >= 2:
            score = 0.8
    elif QUANT_RANK.search(bullet):
        score = 0.5

    # 模糊词惩罚:每个 -0.25
    vague_hits = sum(1 for w in VAGUE_WORDS if w in bullet)
    score -= 0.25 * vague_hits
    return max(0.0, min(1.0, score))


def score_bullet_professional(bullet: str) -> float:
    """
    单条 bullet 的语言专业度,0~1。
    看五件事:动词强度(是否在开头)、长度、第一人称、因果结构、以及**言之有物**。

    最后一项是补的漏:原实现只看句子的"外形"(开头动词 + 字数),
    不看内容。于是 "主导设计行业领先的完美架构,显著提升性能,大幅优化体验"
    这种纯堆砌形容词的句子能拿 0.80 —— 专业动词开头、字数刚好在黄金区间。
    这等于教用户用套话刷分。现在:模糊词和夸大词按个扣分,
    因为"专业"的反面不只是口语化,还包括空话。
    """
    if not bullet:
        return 0.0
    # 短于 10 字的不成句,再专业的动词也撑不起一条 bullet
    if len(bullet) < 10:
        return 0.05
    score = 0.0
    head = bullet[:6]  # 只看开头,避免句中出现 "优化" 就算命中

    if any(v in head for v in VERB_STRONG):
        score += 0.5
    elif any(v in head for v in VERB_NEUTRAL):
        score += 0.35
    elif any(v in head for v in VERB_WEAK):
        score += 0.05
    else:
        # 动词不在开头,但全句有专业动词,给一半
        if any(v in bullet for v in VERB_STRONG | VERB_NEUTRAL):
            score += 0.18

    # 长度:25~60 字是简历 bullet 的黄金区间
    n = len(bullet)
    if 25 <= n <= 60:
        score += 0.3
    elif 15 <= n < 25 or 60 < n <= 80:
        score += 0.15
    # 过短(<15)或过长(>80)不加分

    # 第一人称扣分
    if any(bullet.startswith(p) for p in FIRST_PERSON):
        score -= 0.2

    # 有结果导向的连接(使得/从而/最终)说明写出了因果
    if re.search(r"使得|从而|最终|实现了|支撑了|帮助", bullet):
        score += 0.1

    # 弱动词出现在开头额外扣
    if any(bullet.startswith(v) for v in VERB_WEAK):
        score -= 0.15

    # 空话惩罚:模糊词与夸大词都是"看着专业但没信息量"的典型。
    # 每个模糊词 -0.15、每个夸大词 -0.2,堆砌形容词的句子会被明确压下去。
    score -= 0.15 * sum(1 for w in VAGUE_WORDS if w in bullet)
    score -= 0.2 * sum(1 for w in EXAGGERATION if w in bullet)

    return max(0.0, min(1.0, score))


def score_bullet_credibility(bullet: str) -> float:
    """
    单条 bullet 的可信度贡献,-1~1。
    可验证信号加分,夸大词扣分。
    """
    bullet = bullet[:MAX_SCAN_LEN]
    score = 0.0
    low = bullet.lower()
    if any(sig in low for sig in VERIFIABLE_SIGNALS):
        score += 0.6
    # 具体数字本身也是可信信号
    if QUANT_WITH_UNIT.search(bullet):
        score += 0.3
    # 夸大词
    exagg = sum(1 for w in EXAGGERATION if w in bullet)
    score -= 0.5 * exagg
    # 模糊词也降低可信
    vague = sum(1 for w in VAGUE_WORDS if w in bullet)
    score -= 0.15 * vague
    return max(-1.0, min(1.0, score))
