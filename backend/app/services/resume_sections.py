"""
简历板块定义 —— 对话流程与简历排版共用的唯一来源

对话不再按固定顺序推进,而是把简历拆成若干独立板块:
- 开场先告诉用户简历可以包含哪些板块,由用户自己选择先做哪一块;
- 每完成一块回到"板块选择"(hub)状态,提示还剩下哪些板块;
- 简历正文中各板块的先后顺序由用户自行调整(基本信息固定在页眉)。
"""
import re
from typing import Dict, List, Optional

HUB_STAGE = "section_select"
READY_STAGE = "ready_to_generate"
GENERATE_ACTION = "generate"

# key 同时用作对话阶段名和 session.extracted / 简历 JSON 的字段来源。
SECTIONS: List[Dict] = [
    {
        "key": "basic_info",
        "label": "基本信息",
        "desc": "姓名、联系方式、所在城市",
        "required": True,
        # 页眉固定,不参与正文排序。
        "movable": False,
    },
    {
        "key": "education",
        "label": "教育背景",
        "desc": "学校、专业、学历、毕业时间",
        "required": False,
        "movable": True,
    },
    {
        "key": "experience_mining",
        "label": "项目经历",
        "desc": "项目 / 实习 / 比赛 / 社团,用 STAR-L 法则深挖",
        "required": True,
        "movable": True,
    },
    {
        "key": "skills",
        "label": "专业技能",
        "desc": "技术栈、工具、软技能",
        "required": False,
        "movable": True,
    },
    {
        "key": "awards",
        "label": "获奖荣誉",
        "desc": "奖学金、竞赛奖项、证书",
        "required": False,
        "movable": True,
    },
    {
        "key": "self_evaluation",
        "label": "自我评价",
        "desc": "一两句话概括你的核心优势",
        "required": False,
        "movable": True,
    },
]

SECTION_KEYS = [s["key"] for s in SECTIONS]
SECTION_BY_KEY = {s["key"]: s for s in SECTIONS}
SECTION_LABELS = {s["key"]: s["label"] for s in SECTIONS}
REQUIRED_KEYS = [s["key"] for s in SECTIONS if s["required"]]
# 简历正文默认顺序(基本信息在页眉,不在其中)。
DEFAULT_SECTION_ORDER = [s["key"] for s in SECTIONS if s["movable"]]

GENERATE_LABEL = "生成简历"

# 用户用自然语言选择板块时的关键词;按命中数打分,只命中一个板块才直接采用。
SECTION_KEYWORDS = {
    "basic_info": ["基本信息", "个人信息", "联系方式", "姓名", "手机", "电话", "邮箱", "所在城市", "我叫"],
    "education": ["教育背景", "教育经历", "学校", "学历", "专业", "大学", "学院", "毕业", "本科", "硕士", "研究生", "gpa", "绩点"],
    "experience_mining": ["项目经历", "实践经历", "项目", "实习", "比赛", "竞赛", "社团", "兼职", "志愿", "经历", "工作经验"],
    "skills": ["专业技能", "技能", "技术栈", "工具", "掌握", "熟悉", "会用", "软技能", "编程语言"],
    "awards": ["获奖荣誉", "获奖", "奖学金", "奖项", "荣誉", "证书", "三好", "优秀"],
    "self_evaluation": ["自我评价", "自评", "个人优势", "核心优势", "自我介绍", "评价一下我"],
}

GENERATE_WORDS = ["生成简历", "开始生成", "直接生成", "生成吧", "可以生成", "做简历吧", "输出简历"]

# "先做技能吧" 这类短句表示用户想切换板块,而不是在回答当前问题。
SWITCH_INTENT_WORDS = ["先做", "先填", "先聊", "先说", "先写", "先补", "换到", "切换", "跳到", "去做", "改做", "先从", "先来", "开始做", "做一下"]


def section_label(key: str) -> str:
    return SECTION_LABELS.get(key, key)


def normalize_section_order(order) -> List[str]:
    """Return a full, de-duplicated order of movable sections.

    Unknown keys are dropped and missing keys are appended in default order,
    so the layout can never lose a section merely because the client sent a
    stale or partial list.
    """
    result: List[str] = []
    for key in order or []:
        if key in DEFAULT_SECTION_ORDER and key not in result:
            result.append(key)
    for key in DEFAULT_SECTION_ORDER:
        if key not in result:
            result.append(key)
    return result


def normalize_progress(progress: Optional[Dict]) -> Dict:
    data = progress or {}
    completed = [k for k in (data.get("completed") or []) if k in SECTION_BY_KEY]
    skipped = [
        k for k in (data.get("skipped") or [])
        if k in SECTION_BY_KEY and k not in completed
    ]
    return {
        "completed": list(dict.fromkeys(completed)),
        "skipped": list(dict.fromkeys(skipped)),
        "order": normalize_section_order(data.get("order")),
    }


def mark_section(progress: Dict, key: str, *, skipped: bool = False) -> Dict:
    """Record a section as finished (or explicitly skipped) and return progress."""
    current = normalize_progress(progress)
    completed = [k for k in current["completed"] if k != key]
    skipped_list = [k for k in current["skipped"] if k != key]
    if skipped:
        skipped_list.append(key)
    else:
        completed.append(key)
    current["completed"] = completed
    current["skipped"] = skipped_list
    return current


def remaining_sections(progress: Dict) -> List[Dict]:
    """Sections the user has neither confirmed nor skipped, in display order."""
    current = normalize_progress(progress)
    done = set(current["completed"]) | set(current["skipped"])
    return [s for s in SECTIONS if s["key"] not in done]


def missing_required(progress: Dict) -> List[Dict]:
    current = normalize_progress(progress)
    return [
        SECTION_BY_KEY[k] for k in REQUIRED_KEYS
        if k not in current["completed"]
    ]


def can_generate(progress: Dict) -> bool:
    return not missing_required(progress)


def hub_quick_replies(progress: Dict) -> List[str]:
    replies = [s["label"] for s in remaining_sections(progress)]
    if can_generate(progress):
        replies.append(GENERATE_LABEL)
    return replies


def _section_line(section: Dict, with_desc: bool = False) -> str:
    tag = "(必填)" if section["required"] else ""
    line = f"• **{section['label']}**{tag}"
    if with_desc:
        line += f":{section['desc']}"
    return line


def build_overview_reply(target_job: str) -> str:
    job = target_job or "目标岗位"
    lines = [_section_line(s, with_desc=True) for s in SECTIONS]
    return (
        f"你好!欢迎使用识光简历 ✈️\n\n"
        f"你想做「**{job}**」,这是个很有发展空间的方向。"
        "接下来我会像聊天一样,帮你把简历一块一块地搭起来。\n\n"
        "一份完整的简历通常包含这些板块:\n"
        + "\n".join(lines)
        + "\n\n不用按顺序来——**你想先从哪一块开始?** 点击下方选项,或者直接告诉我。\n"
        "每完成一块,我都会把它写进右侧的简历;正文里各板块的先后位置也可以随时调整,"
        "例如教育背景不够突出,就可以把它挪到简历末尾。"
    )


def build_hub_reply(
    progress: Dict,
    *,
    just_finished: Optional[str] = None,
    skipped: bool = False,
    blocked_generate: bool = False,
    unclear: bool = False,
) -> str:
    """Deterministic "which section next" message shown between sections."""
    current = normalize_progress(progress)
    remaining = remaining_sections(current)
    missing = missing_required(current)
    parts: List[str] = []

    if just_finished:
        label = section_label(just_finished)
        if skipped:
            parts.append(f"好的,已跳过「**{label}**」,之后随时可以回来补充。")
        else:
            parts.append(f"✅ **「{label}」已完成**,已写入右侧简历。")
    elif blocked_generate:
        names = "、".join(f"**{s['label']}**" for s in missing)
        parts.append(f"生成简历前还需要先完成必填板块:{names}。")
    elif unclear:
        parts.append("我暂时没看出你想先做哪一块 🤔")

    if remaining:
        parts.append("还剩下这些板块:\n" + "\n".join(_section_line(s) for s in remaining))
        if missing:
            if just_finished or unclear:
                parts.append("接下来想做哪一块?点击下方选项即可,必填板块完成后就可以生成简历。")
            else:
                parts.append("先从哪一块开始?点击下方选项即可。")
        else:
            parts.append(
                "必填板块都已完成,你可以继续补充剩余板块,也可以现在就点击「生成简历」。"
            )
    else:
        parts.append(
            "🎉 所有板块都已完成!可以点击「生成简历」,或者点击任意板块继续补充修改。"
        )
    return "\n\n".join(parts)


def build_ready_reply() -> str:
    return (
        "好的,信息收集完成 🎯\n\n"
        "我会用 STAR-L 法则重塑你的经历描述,生成一份**专业、量化、可信**的简历,"
        "并附上五维质量评估报告。稍等几秒……"
    )


def _clean(message: str) -> str:
    return (message or "").strip().lower()


def is_generate_request(message: str) -> bool:
    text = _clean(message)
    if not text:
        return False
    if text in {GENERATE_LABEL.lower(), "生成", "开始生成", "生成简历吧", "可以生成了"}:
        return True
    return len(text) <= 16 and any(w in text for w in GENERATE_WORDS)


def infer_section_from_message(message: str) -> Optional[str]:
    """Keyword-based section detection for free text typed at the hub.

    Returns a key only when exactly one section clearly wins; ambiguous or
    empty matches return None so the caller can fall back to an LLM judge.
    """
    text = _clean(message)
    if not text:
        return None
    for key, label in SECTION_LABELS.items():
        if text == label.lower():
            return key
    scores = {
        key: sum(1 for w in words if w.lower() in text)
        for key, words in SECTION_KEYWORDS.items()
    }
    best = max(scores.values())
    if best <= 0:
        return None
    winners = [k for k, v in scores.items() if v == best]
    return winners[0] if len(winners) == 1 else None


def detect_switch_request(message: str) -> Optional[str]:
    """Detect short "先做技能吧" style requests to jump to another section."""
    text = _clean(message)
    if not text or len(text) > 14:
        return None
    if not any(w in text for w in SWITCH_INTENT_WORDS):
        return None
    return infer_section_from_message(re.sub(r"[吧呢啊呀]", "", text))
