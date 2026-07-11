"""
对话服务 —— 状态机推进 + LLM 挖掘式回复

阶段推进策略(方案 C):
- 不再用 user_msg_count 死板映射阶段。
- 每轮先用一次轻量 LLM "judge" 判断用户是否对 AI 上一条信息汇总给出明确确认;
  yes → stage 前进;no → stage 保持不变。
- AI 自己负责在采集完成后 recap 并请用户确认。
"""
import json
import logging
import re
from typing import AsyncGenerator, Dict, List, Optional, Tuple

from app.core.prompts import (
    DIALOG_SYSTEM_PROMPT, STAGE_HINTS, EXTRACT_PROFILE_PROMPT,
    ADVANCE_JUDGE_PROMPT
)
from app.services import llm_service
from app.store.db_store import session_store

logger = logging.getLogger("glint.dialog")


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


def _decide_quick_replies(stage: str) -> List[str]:
    presets = {
        "basic_info": ["李同学,138 0000 0000,上海", "确认", "需要补充"],
        "education": ["本科 2025 届", "硕士 2025 届", "确认"],
        "experience_mining": ["做过一个课程项目", "参加过一场比赛", "确认,没有其他经历了"],
        "awards": ["没有获奖经历", "获得过奖学金", "确认"],
        "skills": ["让 AI 根据经历推断", "确认", "再加几个"],
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

# 用户明确确认词(严格,需要上一条是 recap 才生效)
STRICT_CONFIRM_WORDS = [
    "确认", "无误", "没问题", "没错", "对的", "正确",
    "可以了", "没有其他了", "没有了", "都对", "ok", "OK", "Ok"
]


async def _judge_should_advance(
    current_stage: str,
    last_assistant_msg: str,
    user_message: str
) -> bool:
    """
    阶段推进判定(关键词优先 + LLM 兜底):
    1. 若用户消息**仅为**强制推进词("跳过/下一步") → 直接推进
    2. 若上一条 AI 消息看起来不是 recap → 不推进。
    3. 若上一条是 recap 且用户消息含严格确认词 → 直接推进(不调 LLM,省钱省时)。
    4. 上一条是 recap 但用户消息不明显时,才动 LLM judge。
    """
    if not last_assistant_msg:
        return False

    # 特殊:用户**仅**说"跳过/下一步"(去除标点后长度 ≤ 5),直接推进
    # 避免误判"我曾经跳过二级"这种句子
    clean_msg = user_message.strip().rstrip('。！？,.!?')
    if len(clean_msg) <= 5 and any(k in clean_msg for k in FORCE_ADVANCE_WORDS):
        return True

    looks_like_recap = any(s in last_assistant_msg for s in RECAP_SIGNALS)
    if not looks_like_recap:
        return False  # 上一条还在询问/追问,根本谈不上"确认"

    if any(k in user_message for k in STRICT_CONFIRM_WORDS):
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
            max_tokens=8
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
    session_store.append_message(session_id, "user", user_message)

    current_stage = session.get("stage", "basic_info")

    # 首轮(用户首次说"我想做X"):一定停留在 basic_info,让 AI 询问
    if user_msg_count <= 1 or not last_assistant:
        next_stage = "basic_info"
        advanced = False
    else:
        advance = await _judge_should_advance(current_stage, last_assistant, user_message)
        next_stage = _next_stage(current_stage) if advance else current_stage
        advanced = advance and next_stage != current_stage

    session_store.set_stage(session_id, next_stage)

    stage_hint = STAGE_HINTS.get(next_stage, "")

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
    quick_replies = _decide_quick_replies(next_stage)
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
        async for delta in llm_service.chat_stream(messages, system=system_prompt):
            full_reply_parts.append(delta)
            yield ("delta", json.dumps({"text": delta}, ensure_ascii=False))
    except llm_service.LLMError as e:
        yield ("error", json.dumps({"message": str(e)}, ensure_ascii=False))
        return

    full_reply = "".join(full_reply_parts).strip()
    session_store.append_message(session_id, "assistant", full_reply)

    # ⚠️ 增量提取:如果 AI 刚做完 recap(包含确认信号),尝试提取该阶段数据
    has_recap = any(s in full_reply for s in RECAP_SIGNALS)
    logger.info("chat_stream_done", extra={
        "stage": next_stage,
        "has_recap": has_recap,
        "reply_len": len(full_reply),
    })
    if has_recap:
        await _incremental_extract(session_id, next_stage, full_reply)

    # 把当前已增量抽取的结构化数据一并下发,供前端右侧"实时预览"渲染真实内容
    extracted_snapshot = session_store.get(session_id)
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


async def extract_profile(session_id: str) -> Dict:
    """在生成简历前,基于完整对话历史抽取结构化 profile"""
    session = session_store.get(session_id)
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
        raw = await llm_service.chat_complete(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2
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
    """按标题合并经历:同名经历用新数据覆盖(补充细节),新经历追加在后。
    多段经历分多轮 recap 时,避免后一次提取直接覆盖掉之前已确认的经历。"""
    def norm(t) -> str:
        return (t or "").strip().lower()

    merged = list(existing or [])
    index = {norm(e.get("title")): i for i, e in enumerate(merged) if norm(e.get("title"))}
    for exp in incoming or []:
        key = norm(exp.get("title"))
        if key and key in index:
            merged[index[key]] = exp
        else:
            merged.append(exp)
            if key:
                index[key] = len(merged) - 1
    return merged


async def _incremental_extract(session_id: str, stage: str, ai_recap: str):
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
            raw = await llm_service.chat_complete([{"role": "user", "content": prompt}], temperature=0.1, max_tokens=200)
            data = json.loads(_strip_code_fence(raw))
            session_store.update_extracted(session_id, data)
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
            raw = await llm_service.chat_complete([{"role": "user", "content": prompt}], temperature=0.1, max_tokens=300)
            data = json.loads(_strip_code_fence(raw))
            session_store.update_extracted(session_id, data)
            logger.info("incremental_extract_education", extra={"data": data})
        except Exception as e:
            logger.warning("incremental_extract_education_failed", extra={"error": str(e)})

    elif stage == "experience_mining":
        # 从最近几条消息中提取经历
        session = session_store.get(session_id)
        recent = "\n".join([f"{m['role']}: {m['content']}" for m in session.get("messages", [])[-6:]])
        prompt = f"""从下面对话中,提取用户的项目/实习/比赛经历,输出 JSON:
对话: \"\"\"{recent}\"\"\"

输出格式(只输出 JSON):
{{"experiences": [{{"title": "项目名", "role": "角色", "type": "course_project", "period": "时间", "raw_text": "用户原话", "star_l": {{"situation": "S", "task": "T", "action": "A", "result": "R", "learning": "L"}}}}]}}
"""
        try:
            raw = await llm_service.chat_complete([{"role": "user", "content": prompt}], temperature=0.2, max_tokens=800)
            data = json.loads(_strip_code_fence(raw))
            # ⚠️ 多段经历分多轮 recap 时,合并而非覆盖,避免后一次提取丢掉之前已确认的经历
            existing = (session.get("extracted", {}) or {}).get("experiences", []) if session else []
            merged = _merge_experiences(existing, data.get("experiences", []))
            session_store.update_extracted(session_id, {"experiences": merged})
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
            raw = await llm_service.chat_complete([{"role": "user", "content": prompt}], temperature=0.1, max_tokens=200)
            data = json.loads(_strip_code_fence(raw))
            session_store.update_extracted(session_id, data)
            logger.info("incremental_extract_awards", extra={"data": data})
        except Exception as e:
            logger.warning("incremental_extract_awards_failed", extra={"error": str(e)})

    elif stage == "skills":
        prompt = f"""从下面 AI 的总结中,提取用户的技能,输出 JSON:
AI 总结: \"\"\"{ai_recap}\"\"\"

输出格式(只输出 JSON):
{{"skills": {{"technical": ["技术1", "技术2"], "soft": ["软技能1"]}}}}
"""
        try:
            raw = await llm_service.chat_complete([{"role": "user", "content": prompt}], temperature=0.1, max_tokens=300)
            data = json.loads(_strip_code_fence(raw))
            session_store.update_extracted(session_id, data)
            logger.info("incremental_extract_skills", extra={"data": data})
        except Exception as e:
            logger.warning("incremental_extract_skills_failed", extra={"error": str(e)})
