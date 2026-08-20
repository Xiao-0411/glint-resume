"""
对话服务 —— 状态机推进 + LLM 挖掘式回复

阶段推进策略:
- 不按消息轮数推进,只接受明确确认或用户主动跳过。
- 确认后仍要通过结构化信息完整度门槛,缺关键证据则继续追问。
- 项目经历支持多段循环:确认一段后先询问下一段,明确没有更多经历才推进。
"""
import json
import logging
import re
from typing import AsyncGenerator, Dict, List, Optional, Tuple

from app.core.config import settings
from app.core.prompts import (
    DIALOG_SYSTEM_PROMPT, STAGE_HINTS, EXTRACT_PROFILE_PROMPT,
    ADVANCE_JUDGE_PROMPT
)
from app.services import llm_service
from app.store.db_store import session_store

logger = logging.getLogger("glint.dialog")


def _store_get(session_id: str, user_id: Optional[str] = None):
    if user_id is None:
        return session_store.get(session_id)
    try:
        return session_store.get(session_id, user_id)
    except TypeError:
        return session_store.get(session_id)


def _store_append(session_id: str, role: str, content: str, user_id: Optional[str] = None):
    if user_id is None:
        return session_store.append_message(session_id, role, content)
    try:
        return session_store.append_message(session_id, role, content, user_id)
    except TypeError:
        return session_store.append_message(session_id, role, content)


def _store_stage(session_id: str, stage: str, user_id: Optional[str] = None):
    if user_id is None:
        return session_store.set_stage(session_id, stage)
    try:
        return session_store.set_stage(session_id, stage, user_id)
    except TypeError:
        return session_store.set_stage(session_id, stage)


def _store_extracted(session_id: str, info: Dict, user_id: Optional[str] = None):
    if user_id is None:
        return session_store.update_extracted(session_id, info)
    try:
        return session_store.update_extracted(session_id, info, user_id)
    except TypeError:
        return session_store.update_extracted(session_id, info)


STAGE_ORDER = [
    "basic_info", "education",
    "experience_mining",
    "awards", "skills", "ready_to_generate"
]

STAGE_LABELS = {
    "basic_info": "基本信息",
    "education": "教育背景",
    "experience_mining": "项目经历",
    "skills": "技能",
    "awards": "获奖",
    "ready_to_generate": "准备生成"
}

def _next_stage(current: str) -> str:
    try:
        idx = STAGE_ORDER.index(current)
    except ValueError:
        return STAGE_ORDER[0]
    return STAGE_ORDER[min(idx + 1, len(STAGE_ORDER) - 1)]


def _decide_quick_replies(
    stage: str,
    gaps: Optional[List[str]] = None,
    experience_confirmed: bool = False,
) -> List[str]:
    if experience_confirmed:
        return ["还有一段课程/个人项目", "还有实习或社团经历", "没有其他经历了"]
    if gaps:
        if stage == "experience_mining":
            return ["我补充具体行动", "结果可以用范围描述", "这部分我暂时想不起来"]
        return ["我来补充", "这项暂时没有", "帮我举个例子"]

    presets = {
        "basic_info": ["李同学,138 0000 0000,上海", "确认", "需要补充"],
        "education": ["我补充学校和专业", "我补充学历和毕业时间", "确认"],
        "experience_mining": ["做过一个课程项目", "有过实习/兼职", "参加过比赛或社团"],
        "awards": ["没有获奖经历", "获得过奖学金", "确认"],
        "skills": ["根据经历帮我梳理", "我补充使用场景", "确认"],
        "ready_to_generate": []
    }
    return presets.get(stage, [])


def _build_messages_for_llm(session: Dict) -> List[Dict]:
    """从 session 历史构造 LLM 输入 messages 列表。
    用户消息已在 prepare_stage_info 中追加进 session,此处不再重复添加,
    否则会向 LLM 连续发送两条完全相同的 user 消息。"""
    return list(session.get("messages", []))


def _last_assistant_msg(session: Dict) -> str:
    for m in reversed(session.get("messages", [])):
        if m.get("role") == "assistant":
            return m.get("content", "")
    return ""


# AI recap 的语言特征,用以判断"上一条是不是 recap"
RECAP_SIGNALS = [
    "是否准确", "请确认", "如无误", "需要补充", "需要修改",
    "是否还有其他", "以上信息", "回复\"确认\"", "回复'确认'"
]

# 强制推进关键词(无论上一条是否 recap 都推进)
FORCE_ADVANCE_WORDS = ["跳过", "下一步", "往下走", "下一个", "继续下一个"]

CONFIRMATION_ONLY_MESSAGES = {
    "确认", "无误", "没问题", "没错", "对", "对的", "正确",
    "可以", "可以了", "都对", "好", "好的", "ok"
}

NO_MORE_EXPERIENCE_WORDS = [
    "没有其他", "没有别的", "没有更多", "就这些", "就这一段",
    "暂时没有", "没有了", "没了", "无其他"
]


def _clean_user_message(message: str) -> str:
    return (message or "").strip().rstrip("。！？,.!?")


def _is_force_advance(message: str) -> bool:
    clean_msg = _clean_user_message(message)
    return len(clean_msg) <= 5 and any(k in clean_msg for k in FORCE_ADVANCE_WORDS)


def _is_no_more_experience(message: str) -> bool:
    clean_msg = _clean_user_message(message)
    return any(word in clean_msg for word in NO_MORE_EXPERIENCE_WORDS)


def _is_confirmation_only(message: str) -> bool:
    clean_msg = _clean_user_message(message).lower()
    if clean_msg in CONFIRMATION_ONLY_MESSAGES:
        return True
    # "确认，没有其他经历了" is still a confirmation, while a longer
    # sentence containing new details must stay in the current stage.
    return len(clean_msg) <= 18 and _is_no_more_experience(clean_msg)


def _has_value(value) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, dict)):
        return bool(value)
    return True


def _stage_gaps(stage: str, extracted: Optional[Dict]) -> List[str]:
    """Return resume-critical gaps that must be filled before confirmation advances."""
    data = extracted or {}

    if stage == "basic_info":
        gaps = []
        if not _has_value(data.get("fullname")):
            gaps.append("姓名")
        if not (_has_value(data.get("phone")) or _has_value(data.get("email"))):
            gaps.append("至少一种联系方式")
        if not _has_value(data.get("location")):
            gaps.append("所在城市")
        return gaps

    if stage == "education":
        education = data.get("education") or []
        if not education:
            return ["学校", "专业", "学历", "毕业时间"]
        latest = education[-1] or {}
        fields = [
            ("school", "学校"),
            ("major", "专业"),
            ("degree", "学历"),
            ("period", "毕业时间"),
        ]
        return [label for key, label in fields if not _has_value(latest.get(key))]

    if stage == "experience_mining":
        experiences = data.get("experiences") or []
        if not experiences:
            return ["至少一段可用于简历的经历"]
        current = experiences[-1] or {}
        star = current.get("star_l") or {}
        gaps = []
        if not _has_value(current.get("title")):
            gaps.append("经历名称")
        if not _has_value(current.get("period")):
            gaps.append("经历时间")
        if not _has_value(star.get("situation")):
            gaps.append("背景和目标")
        if not (_has_value(current.get("role")) or _has_value(star.get("task"))):
            gaps.append("个人职责")
        if not _has_value(star.get("action")):
            gaps.append("关键行动和难点解决")
        if not _has_value(star.get("result")):
            gaps.append("结果或成果证据")
        if not _has_value(star.get("learning")):
            gaps.append("复盘与成长")
        return gaps

    if stage == "awards":
        return [] if "awards" in data else ["获奖情况（可以明确填写无）"]

    if stage == "skills":
        skills = data.get("skills") or {}
        skill_values = []
        for key in ("technical", "tools", "product", "soft"):
            skill_values.extend(skills.get(key) or [])
        return [] if skill_values else ["至少一项有实际使用证据的技能"]

    return []


async def _judge_should_advance(
    current_stage: str,
    last_assistant_msg: str,
    user_message: str
) -> bool:
    """
    阶段推进判定(关键词优先 + LLM 兜底):
    1. 若用户消息**仅为**强制推进词("跳过/下一步") → 直接推进
    2. 若上一条 AI 消息看起来不是 recap → 不推进。
    3. 若上一条是 recap 且用户整句话是明确确认 → 直接推进(不调 LLM,省钱省时)。
    4. 上一条是 recap 但用户消息不明显时,才动 LLM judge。
    """
    if not last_assistant_msg:
        return False

    # 特殊:用户**仅**说"跳过/下一步"(去除标点后长度 ≤ 5),直接推进
    # 避免误判"我曾经跳过二级"这种句子
    if _is_force_advance(user_message):
        return True

    if current_stage == "experience_mining" and _is_no_more_experience(user_message):
        return True

    looks_like_recap = any(s in last_assistant_msg for s in RECAP_SIGNALS)
    if not looks_like_recap:
        return False  # 上一条还在询问/追问,根本谈不上"确认"

    if _is_confirmation_only(user_message):
        return True

    # 模糊情形:上一条是 recap,但用户没说明确确认词 → 让 LLM 兜底判一下
    try:
        raw = await llm_service.chat_complete(
            messages=[{
                "role": "user",
                "content": ADVANCE_JUDGE_PROMPT.format(
                    current_stage=current_stage,
                    last_assistant_msg=last_assistant_msg[-800:],
                    user_message=user_message[:400]
                )
            }],
            temperature=0.0,
            max_tokens=8,
            model=settings.LLM_MODEL_FAST,
            timeout=settings.LLM_TIMEOUT_FAST_SECONDS,
        )
        verdict = raw.strip().lower()
        return any(v in verdict for v in ["yes", "是", "true"])
    except llm_service.LLMError:
        return False


async def prepare_stage_info(
    session_id: str,
    target_job: str,
    user_message: str,
    user_msg_count: int,
    user_id: Optional[str] = None,
) -> Tuple[Dict, str, str, List[str]]:
    """
    在 LLM 主回复前,先确定下一阶段,组装 system prompt
    返回: (session, next_stage, system_prompt, quick_replies)
    """
    session = session_store.get_or_create(session_id, target_job, user_id)

    # 在 append 用户消息之前抓取 last_assistant(judge 需要)
    last_assistant = _last_assistant_msg(session)

    # 记录用户消息
    _store_append(session_id, "user", user_message, user_id)

    current_stage = session.get("stage", "basic_info")
    current_gaps = _stage_gaps(current_stage, session.get("extracted", {}))
    blocked_gaps: List[str] = []
    experience_confirmed = False

    # 首轮(用户首次说"我想做X"):一定停留在 basic_info,让 AI 询问
    if user_msg_count <= 1 or not last_assistant:
        next_stage = "basic_info"
        advanced = False
    else:
        advance = await _judge_should_advance(current_stage, last_assistant, user_message)
        force_advance = _is_force_advance(user_message)
        if advance and current_gaps and not force_advance:
            next_stage = current_stage
            advanced = False
            blocked_gaps = current_gaps
        elif (
            advance
            and current_stage == "experience_mining"
            and not force_advance
            and not _is_no_more_experience(user_message)
        ):
            # Confirming one experience completes that item, not the whole section.
            # Ask for another experience before leaving the deepest resume section.
            next_stage = current_stage
            advanced = False
            experience_confirmed = True
        else:
            next_stage = _next_stage(current_stage) if advance else current_stage
            advanced = advance and next_stage != current_stage

    _store_stage(session_id, next_stage, user_id)

    stage_hint = STAGE_HINTS.get(next_stage, "")

    if blocked_gaps:
        stage_hint += (
            "\n\n# 系统质量门槛（必须执行）\n"
            f"用户刚才想确认，但当前阶段仍缺少：{'、'.join(blocked_gaps)}。\n"
            "- 不要接受本次确认，也不要重复整段总结。\n"
            "- 先温和说明还差哪些关键信息，本轮只追问其中最重要的 1~2 项。\n"
            "- 问题必须具体，并给出可回忆的角度；用户确实没有时允许其明确说没有或主动跳过。"
        )
    elif experience_confirmed:
        stage_hint += (
            "\n\n# 当前经历已确认\n"
            "用户已确认刚才那一段经历。本轮不要重复 recap，也不要继续追问同一段。"
            "只询问是否还有第二段值得写入简历的经历，并提示课程项目、个人作品、实习兼职、"
            "比赛、社团或志愿活动都可以。用户明确说没有其他经历后，系统会在下一轮推进。"
        )

    # 当阶段刚刚推进时,在 hint 末尾追加一条强约束,
    # 防止 AI 因对话历史惯性又退回上一阶段重复 recap。
    if advanced:
        prev_label = STAGE_LABELS.get(current_stage, current_stage)
        new_label = STAGE_LABELS.get(next_stage, next_stage)
        stage_hint += (
            f"\n\n⚠️ 注意:用户刚刚确认完成上一阶段「{prev_label}」,"
            f"现在你必须立刻切换到「{new_label}」环节。\n"
            f"- 严禁再次 recap 或讨论「{prev_label}」相关内容(无论对话历史里有多少相关讨论)。\n"
            f"- 直接以一句过渡(例如\"好的,基本信息收到 ✅,接下来......\")开头,"
            f"然后开始「{new_label}」的引导/提问。"
        )

    system_prompt = DIALOG_SYSTEM_PROMPT.format(
        target_job=target_job or session.get("target_job") or "未指定岗位",
        stage_hint=stage_hint
    )
    quick_replies = _decide_quick_replies(
        next_stage,
        gaps=blocked_gaps,
        experience_confirmed=experience_confirmed,
    )
    # 重新读取:session 是 append_message 之前的快照,不含本轮用户消息。
    # 直接用旧快照会导致首轮 messages 为空,LLM 请求被网关拒绝。
    session = _store_get(session_id, user_id) or session
    return session, next_stage, system_prompt, quick_replies


async def chat_stream(
    session_id: str,
    target_job: str,
    user_message: str,
    user_msg_count: int,
    user_id: Optional[str] = None,
) -> AsyncGenerator[Tuple[str, str], None]:
    """
    流式生成 AI 回复
    yield (event_type, payload_json):
      - ('delta', '{"text": "片段"}')
      - ('done', '{"stage": "...", "stage_label": "...", "quick_replies": [...]}')
      - ('error', '{"message": "..."}')
    """
    session, next_stage, system_prompt, quick_replies = await prepare_stage_info(
        session_id, target_job, user_message, user_msg_count, user_id
    )

    messages = _build_messages_for_llm(session)

    full_reply_parts: List[str] = []
    try:
        async for delta in llm_service.chat_stream(
            messages,
            system=system_prompt,
            model=settings.LLM_MODEL_FAST,
            timeout=settings.LLM_TIMEOUT_FAST_SECONDS,
        ):
            full_reply_parts.append(delta)
            yield ("delta", json.dumps({"text": delta}, ensure_ascii=False))
    except llm_service.LLMError as e:
        yield ("error", json.dumps({"message": str(e)}, ensure_ascii=False))
        return

    full_reply = "".join(full_reply_parts).strip()
    _store_append(session_id, "assistant", full_reply, user_id)

    # ⚠️ 增量提取:如果 AI 刚做完 recap(包含确认信号),尝试提取该阶段数据
    has_recap = any(s in full_reply for s in RECAP_SIGNALS)
    logger.info("chat_stream_done", extra={
        "stage": next_stage,
        "has_recap": has_recap,
        "reply_len": len(full_reply),
    })
    if has_recap:
        await _incremental_extract(session_id, next_stage, full_reply, user_id)

    # 把当前已增量抽取的结构化数据一并下发,供前端右侧"实时预览"渲染真实内容
    extracted_snapshot = _store_get(session_id, user_id)
    extracted = extracted_snapshot.get("extracted", {}) if extracted_snapshot else {}

    yield (
        "done",
        json.dumps({
            "stage": next_stage,
            "stage_label": STAGE_LABELS.get(next_stage, ""),
            "quick_replies": quick_replies,
            "extracted": extracted
        }, ensure_ascii=False)
    )


async def extract_profile(session_id: str, user_id: Optional[str] = None) -> Dict:
    """在生成简历前,基于完整对话历史抽取结构化 profile"""
    session = _store_get(session_id, user_id)
    if not session:
        logger.warning("extract_profile_session_not_found", extra={"session_id": session_id})
        return {}

    history_text = "\n".join(
        f"{m['role'].upper()}: {m['content']}"
        for m in session.get("messages", [])
    )
    logger.info("extract_profile_start", extra={"history_len": len(history_text)})
    prompt = EXTRACT_PROFILE_PROMPT.format(dialog_history=history_text)
    try:
        # 整段对话历史是个大 prompt,pro 上实测会跑到网关 524 超时;
        # 这一步是信息抽取而非文案创作,用快模型足够且稳定。
        raw = await llm_service.chat_complete(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            model=settings.LLM_MODEL_FAST,
            timeout=settings.LLM_TIMEOUT_FAST_SECONDS,
        )
        logger.debug("extract_profile_raw", extra={"raw_preview": raw[:200]})
        cleaned = _strip_code_fence(raw)
        profile = json.loads(cleaned)
        logger.info("extract_profile_success", extra={
            "fullname": profile.get("fullname", "N/A"),
            "experience_count": len(profile.get("experiences", [])),
        })
        return profile
    except (llm_service.LLMError, json.JSONDecodeError) as e:
        logger.error("extract_profile_failed", extra={
            "error_type": type(e).__name__,
            "error": str(e),
        })
        return {}


def _strip_code_fence(text: str) -> str:
    """去掉 ```json ... ``` 包裹"""
    s = text.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    return s.strip()


def _merge_experiences(existing: List[Dict], incoming: List[Dict]) -> List[Dict]:
    """按标题合并经历,并保留后续抽取中暂时缺失的既有细节。"""
    def norm(t) -> str:
        return (t or "").strip().lower()

    def merge_non_empty(old: Dict, new: Dict) -> Dict:
        result = dict(old or {})
        for key, value in (new or {}).items():
            if isinstance(value, dict):
                result[key] = merge_non_empty(result.get(key) or {}, value)
            elif _has_value(value):
                result[key] = value
        return result

    merged = list(existing or [])
    index = {norm(e.get("title")): i for i, e in enumerate(merged) if norm(e.get("title"))}
    for exp in incoming or []:
        key = norm(exp.get("title"))
        if key and key in index:
            merged[index[key]] = merge_non_empty(merged[index[key]], exp)
        else:
            merged.append(exp)
            if key:
                index[key] = len(merged) - 1
    return merged


async def _incremental_extract(
    session_id: str,
    stage: str,
    ai_recap: str,
    user_id: Optional[str] = None,
):
    """
    增量提取:根据当前阶段和 AI 的 recap,提取结构化数据存入 session
    """
    logger.info("incremental_extract_start", extra={"stage": stage, "recap_len": len(ai_recap)})

    if stage == "basic_info":
        # 从 AI recap 中提取姓名/电话/邮箱/城市
        prompt = f"""从下面 AI 的总结中,提取用户的基本信息,输出 JSON:
AI 总结: \"\"\"{ai_recap}\"\"\"

输出格式(只输出 JSON,不要其他文字):
{{"fullname": "姓名", "phone": "手机号", "email": "邮箱", "location": "城市"}}
"""
        try:
            raw = await llm_service.chat_complete(
                [{"role": "user", "content": prompt}], temperature=0.1, max_tokens=200,
                model=settings.LLM_MODEL_FAST, timeout=settings.LLM_TIMEOUT_FAST_SECONDS)
            data = json.loads(_strip_code_fence(raw))
            _store_extracted(session_id, data, user_id)
            logger.info("incremental_extract_basic_info", extra={"data": data})
        except Exception as e:
            logger.warning("incremental_extract_basic_info_failed", extra={"error": str(e)})

    elif stage == "education":
        prompt = f"""从下面 AI 的总结中,提取用户的教育背景,输出 JSON 数组:
AI 总结: \"\"\"{ai_recap}\"\"\"

输出格式(只输出 JSON,不要其他文字):
{{"education": [{{"school": "学校", "major": "专业", "degree": "本科/硕士", "period": "时间", "gpa": "GPA", "highlights": []}}]}}
"""
        try:
            raw = await llm_service.chat_complete(
                [{"role": "user", "content": prompt}], temperature=0.1, max_tokens=300,
                model=settings.LLM_MODEL_FAST, timeout=settings.LLM_TIMEOUT_FAST_SECONDS)
            data = json.loads(_strip_code_fence(raw))
            _store_extracted(session_id, data, user_id)
            logger.info("incremental_extract_education", extra={"data": data})
        except Exception as e:
            logger.warning("incremental_extract_education_failed", extra={"error": str(e)})

    elif stage == "experience_mining":
        # 从最近几条消息中提取经历
        session = _store_get(session_id, user_id)
        recent = "\n".join([f"{m['role']}: {m['content']}" for m in session.get("messages", [])[-14:]])
        prompt = f"""从下面对话中,提取用户的项目/实习/比赛/社团经历,输出 JSON:
对话: \"\"\"{recent}\"\"\"

抽取规则:
- 只记录用户明确表达过的信息,禁止补写用户没有提供的数字、结果或职责。
- 尽量保留经历名称、时间、个人角色,并将背景/目标、个人任务、关键行动、结果证据、复盘成长分别放入 STAR-L。
- 某项尚未提到时填空字符串,不要用常识猜测。

输出格式(只输出 JSON):
{{"experiences": [{{"title": "项目名", "role": "角色", "type": "course_project", "period": "时间", "raw_text": "用户原话", "star_l": {{"situation": "S", "task": "T", "action": "A", "result": "R", "learning": "L"}}}}]}}
"""
        try:
            raw = await llm_service.chat_complete(
                [{"role": "user", "content": prompt}], temperature=0.2, max_tokens=800,
                model=settings.LLM_MODEL_FAST, timeout=settings.LLM_TIMEOUT_FAST_SECONDS)
            data = json.loads(_strip_code_fence(raw))
            # ⚠️ 多段经历分多轮 recap 时,合并而非覆盖,避免后一次提取丢掉之前已确认的经历
            existing = (session.get("extracted", {}) or {}).get("experiences", []) if session else []
            merged = _merge_experiences(existing, data.get("experiences", []))
            _store_extracted(session_id, {"experiences": merged}, user_id)
            logger.info("incremental_extract_experience", extra={"merged_count": len(merged)})
        except Exception as e:
            logger.warning("incremental_extract_experience_failed", extra={"error": str(e)})

    elif stage == "awards":
        prompt = f"""从下面 AI 的总结中,提取用户的获奖荣誉,输出 JSON 数组:
AI 总结: \"\"\"{ai_recap}\"\"\"

输出格式(只输出 JSON):
{{"awards": ["奖项1", "奖项2"]}}
"""
        try:
            raw = await llm_service.chat_complete(
                [{"role": "user", "content": prompt}], temperature=0.1, max_tokens=200,
                model=settings.LLM_MODEL_FAST, timeout=settings.LLM_TIMEOUT_FAST_SECONDS)
            data = json.loads(_strip_code_fence(raw))
            _store_extracted(session_id, data, user_id)
            logger.info("incremental_extract_awards", extra={"data": data})
        except Exception as e:
            logger.warning("incremental_extract_awards_failed", extra={"error": str(e)})

    elif stage == "skills":
        prompt = f"""从下面 AI 的总结中,提取用户的技能,输出 JSON:
AI 总结: \"\"\"{ai_recap}\"\"\"

输出格式(只输出 JSON):
{{"skills": {{"technical": ["技术1", "技术2"], "tools": ["工具1"], "product": ["产品/设计能力"], "soft": ["软技能1"]}}}}
"""
        try:
            raw = await llm_service.chat_complete(
                [{"role": "user", "content": prompt}], temperature=0.1, max_tokens=300,
                model=settings.LLM_MODEL_FAST, timeout=settings.LLM_TIMEOUT_FAST_SECONDS)
            data = json.loads(_strip_code_fence(raw))
            _store_extracted(session_id, data, user_id)
            logger.info("incremental_extract_skills", extra={"data": data})
        except Exception as e:
            logger.warning("incremental_extract_skills_failed", extra={"error": str(e)})
