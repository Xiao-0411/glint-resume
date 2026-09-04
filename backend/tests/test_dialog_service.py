import json
import unittest
from unittest.mock import AsyncMock, patch

from app.services import dialog_service, llm_service


def complete_experience():
    return {
        "title": "校园二手交易平台",
        "role": "产品负责人",
        "period": "2025.03-2025.06",
        "star_l": {
            "situation": "课程项目需要解决校内闲置物品流通问题",
            "task": "负责需求分析和核心流程设计",
            "action": "访谈学生并重构发布流程，协调三人完成迭代",
            "result": "完成上线并获得课程优秀评价",
            "learning": "掌握了从用户问题到产品方案的验证方法",
        },
    }


class FakeSessionStore:
    def __init__(self, session):
        self.session = session

    def get_or_create(self, session_id, target_job="", user_id=None):
        return self.session

    def append_message(self, session_id, role, content):
        self.session["messages"].append({"role": role, "content": content})

    def set_stage(self, session_id, stage):
        self.session["stage"] = stage

    def get(self, session_id):
        return self.session


class StageGapTests(unittest.TestCase):
    def test_experience_requires_resume_ready_evidence(self):
        gaps = dialog_service._stage_gaps("experience_mining", {
            "experiences": [{
                "title": "课程项目",
                "role": "组员",
                "period": "2025",
                "star_l": {"situation": "完成课程作业"},
            }]
        })

        self.assertIn("关键行动和难点解决", gaps)
        self.assertIn("结果或成果证据", gaps)
        self.assertIn("复盘与成长", gaps)

    def test_complete_experience_has_no_gaps(self):
        gaps = dialog_service._stage_gaps("experience_mining", {
            "experiences": [complete_experience()]
        })
        self.assertEqual(gaps, [])

    def test_confirmation_with_new_details_is_not_confirmation_only(self):
        self.assertFalse(dialog_service._is_confirmation_only(
            "没问题，我还补充一个自己负责的用户访谈"
        ))

    def test_partial_re_extraction_preserves_existing_experience_details(self):
        existing = [complete_experience()]
        incoming = [{
            "title": existing[0]["title"],
            "role": "",
            "period": "",
            "star_l": {"result": "课程展示获得前三名", "learning": ""},
        }]

        merged = dialog_service._merge_experiences(existing, incoming)

        self.assertEqual(merged[0]["role"], existing[0]["role"])
        self.assertEqual(merged[0]["star_l"]["action"], existing[0]["star_l"]["action"])
        self.assertEqual(merged[0]["star_l"]["result"], "课程展示获得前三名")

    def test_second_experience_is_appended(self):
        existing = [complete_experience()]
        incoming = [{
            "title": "Campus Design Competition",
            "period": "2025.07",
            "star_l": {},
        }]

        merged = dialog_service._merge_experiences(existing, incoming)

        self.assertEqual(len(merged), 2)
        self.assertEqual(merged[1]["title"], "Campus Design Competition")

    def test_project_recap_overrides_lagging_education_stage(self):
        recap = """
        - 项目名称：智能 Agent 系统
        - 核心功能：读取、修改并执行服务器命令
        - 个人角色：独立开发
        - 技术栈：Spring Boot + DeepSeek API
        """

        stage = dialog_service._infer_extraction_stage("education", recap)

        self.assertEqual(stage, "experience_mining")

    def test_single_technical_keyword_does_not_override_education_stage(self):
        recap = "学校课程中使用过 Java，以上教育信息是否准确？"

        stage = dialog_service._infer_extraction_stage("education", recap)

        self.assertEqual(stage, "education")

    def test_continuation_overlap_is_removed(self):
        existing = "这段经历能体现你的独立开发能力"
        continuation = "独立开发能力，也能体现真实落地经验。"

        result = dialog_service._trim_continuation_overlap(existing, continuation)

        self.assertEqual(result, "，也能体现真实落地经验。")

    def test_recap_is_not_committed_without_confirmation(self):
        recap = "- 姓名：肖伟众\n以上信息是否准确？如无误请回复“确认”。"

        self.assertFalse(dialog_service._should_commit_recap(
            "basic_info", recap, "我还要补充一下邮箱"
        ))

    def test_recap_is_committed_only_after_confirmation(self):
        recap = "- 姓名：肖伟众\n以上信息是否准确？如无误请回复“确认”。"

        self.assertTrue(dialog_service._should_commit_recap(
            "basic_info", recap, "确认"
        ))

    def test_opening_quote_is_detected_as_truncated(self):
        partial = "以上信息是否准确？如无误请回复“"

        self.assertTrue(dialog_service._reply_needs_continuation(partial))
        self.assertFalse(dialog_service._reply_looks_complete(partial))

    def test_unmatched_ascii_quote_is_detected_as_truncated(self):
        partial = '以上信息是否准确？如无误请回复"'

        self.assertTrue(dialog_service._reply_needs_continuation(partial))
        self.assertFalse(dialog_service._reply_looks_complete(partial))

    def test_unfinished_function_word_is_detected_as_truncated(self):
        partial = "之后正式投递时"

        self.assertTrue(dialog_service._reply_needs_continuation(partial))
        self.assertFalse(dialog_service._reply_looks_complete(partial))

    def test_unfinished_conjunction_is_detected_as_truncated(self):
        partial = "如果你有特别想去的目标城市，也可以一并"

        self.assertTrue(dialog_service._reply_needs_continuation(partial))
        self.assertFalse(dialog_service._reply_looks_complete(partial))

    def test_closed_markdown_is_not_treated_as_truncated(self):
        self.assertFalse(dialog_service._reply_needs_continuation("请确认 **基本信息**"))
        self.assertTrue(dialog_service._reply_needs_continuation("请确认 **基本信息"))


class StageTransitionTests(unittest.IsolatedAsyncioTestCase):
    def make_session(self, extracted):
        return {
            "session_id": "test-session",
            "target_job": "产品经理",
            "messages": [{
                "role": "assistant",
                "content": "以上是这段经历的总结，是否准确？如无误请回复确认。",
            }],
            "stage": "experience_mining",
            "extracted": extracted,
        }

    async def prepare(self, session, message):
        store = FakeSessionStore(session)
        with patch.object(dialog_service, "session_store", store):
            return await dialog_service.prepare_stage_info(
                "test-session",
                "产品经理",
                message,
                user_msg_count=3,
                user_id="user-1",
            )

    async def test_incomplete_experience_blocks_confirmation(self):
        session = self.make_session({
            "experiences": [{
                "title": "课程项目",
                "role": "组员",
                "period": "2025",
                "star_l": {"situation": "课程要求"},
            }]
        })

        _, stage, system_prompt, replies = await self.prepare(session, "确认")

        self.assertEqual(stage, "experience_mining")
        self.assertIn("系统质量门槛", system_prompt)
        self.assertIn("结果或成果证据", system_prompt)
        self.assertIn("我补充具体行动", replies)

    async def test_confirmed_experience_asks_for_another(self):
        session = self.make_session({"experiences": [complete_experience()]})

        _, stage, system_prompt, replies = await self.prepare(session, "确认")

        self.assertEqual(stage, "experience_mining")
        self.assertIn("当前经历已确认", system_prompt)
        self.assertIn("没有其他经历了", replies)

    async def test_no_more_experience_advances(self):
        session = self.make_session({"experiences": [complete_experience()]})
        session["messages"][-1]["content"] = "这段经历已确认。还有其他经历要补充吗？"

        _, stage, system_prompt, _ = await self.prepare(session, "没有其他经历了")

        self.assertEqual(stage, "awards")
        self.assertIn("现在你必须立刻切换到「获奖」", system_prompt)

    async def test_force_advance_bypasses_quality_gate(self):
        session = self.make_session({})

        _, stage, _, _ = await self.prepare(session, "下一步")

        self.assertEqual(stage, "awards")


class StreamRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_incomplete_stream_is_continued_before_done(self):
        session = {
            "session_id": "test-session",
            "target_job": "Java 后端",
            "messages": [{"role": "user", "content": "介绍一下项目"}],
            "stage": "experience_mining",
            "extracted": {},
        }
        store = FakeSessionStore(session)

        async def interrupted_stream(*args, **kwargs):
            yield "这段经历可以体现你的"
            raise llm_service.LLMStreamIncomplete(
                "达到输出上限",
                reason="max_tokens",
                partial_text="这段经历可以体现你的",
            )

        with (
            patch.object(dialog_service, "session_store", store),
            patch.object(
                dialog_service,
                "prepare_stage_info",
                AsyncMock(return_value=(session, "experience_mining", "system", [])),
            ),
            patch.object(dialog_service.llm_service, "chat_stream", interrupted_stream),
            patch.object(
                dialog_service.llm_service,
                "chat_complete",
                AsyncMock(return_value="独立开发能力。"),
            ),
        ):
            events = [
                (event_name, json.loads(payload))
                async for event_name, payload in dialog_service.chat_stream(
                    "test-session", "Java 后端", "介绍一下项目", 3, "user-1"
                )
            ]

        deltas = [payload["text"] for name, payload in events if name == "delta"]
        self.assertEqual("".join(deltas), "这段经历可以体现你的独立开发能力。")
        self.assertEqual(events[-1][0], "done")
        self.assertEqual(
            session["messages"][-1]["content"],
            "这段经历可以体现你的独立开发能力。",
        )

    async def test_normal_stop_with_opening_quote_is_continued(self):
        session = {
            "session_id": "test-session",
            "target_job": "产品经理",
            "messages": [{"role": "user", "content": "补充基本信息"}],
            "stage": "basic_info",
            "extracted": {},
        }
        store = FakeSessionStore(session)

        async def completed_but_cut_off(*args, **kwargs):
            yield "以上信息是否准确？如无误请回复“"

        with (
            patch.object(dialog_service, "session_store", store),
            patch.object(
                dialog_service,
                "prepare_stage_info",
                AsyncMock(return_value=(session, "basic_info", "system", [])),
            ),
            patch.object(dialog_service.llm_service, "chat_stream", completed_but_cut_off),
            patch.object(
                dialog_service.llm_service,
                "chat_complete",
                AsyncMock(return_value="确认”。"),
            ),
        ):
            events = [
                (event_name, json.loads(payload))
                async for event_name, payload in dialog_service.chat_stream(
                    "test-session", "产品经理", "补充基本信息", 2, "user-1"
                )
            ]

        deltas = [payload["text"] for name, payload in events if name == "delta"]
        self.assertEqual("".join(deltas), "以上信息是否准确？如无误请回复“确认”。")
        self.assertEqual(events[-1][0], "done")
        self.assertEqual(
            session["messages"][-1]["content"],
            "以上信息是否准确？如无误请回复“确认”。",
        )

    async def test_normal_stop_on_function_word_is_continued(self):
        session = {
            "session_id": "test-session",
            "target_job": "市场运营",
            "messages": [{"role": "user", "content": "我想做市场运营"}],
            "stage": "basic_info",
            "extracted": {},
        }
        store = FakeSessionStore(session)

        async def completed_but_semantically_cut_off(*args, **kwargs):
            yield "这些信息会帮助你在之后正式投递时"

        with (
            patch.object(dialog_service, "session_store", store),
            patch.object(
                dialog_service,
                "prepare_stage_info",
                AsyncMock(return_value=(session, "basic_info", "system", [])),
            ),
            patch.object(dialog_service.llm_service, "chat_stream", completed_but_semantically_cut_off),
            patch.object(
                dialog_service.llm_service,
                "chat_complete",
                AsyncMock(return_value="补充完整简历信息。"),
            ),
        ):
            events = [
                (event_name, json.loads(payload))
                async for event_name, payload in dialog_service.chat_stream(
                    "test-session", "市场运营", "我想做市场运营", 2, "user-1"
                )
            ]

        deltas = [payload["text"] for name, payload in events if name == "delta"]
        self.assertEqual("".join(deltas), "这些信息会帮助你在之后正式投递时补充完整简历信息。")
        self.assertEqual(events[-1][0], "done")


class LLMFinishReasonTests(unittest.TestCase):
    def test_anthropic_length_stop_is_detected(self):
        reason = llm_service._extract_stop_reason({
            "type": "message_delta",
            "delta": {"stop_reason": "max_tokens"},
        })

        self.assertEqual(reason, "max_tokens")
        self.assertTrue(llm_service._is_length_stop(reason))


class StructuredChatResponseTests(unittest.IsolatedAsyncioTestCase):
    def make_session(self):
        return {
            "session_id": "test-session",
            "target_job": "市场运营",
            "messages": [{"role": "user", "content": "我想做市场运营"}],
            "stage": "basic_info",
            "extracted": {},
        }

    async def test_structured_response_is_committed_only_after_validation(self):
        session = self.make_session()
        store = FakeSessionStore(session)
        with (
            patch.object(dialog_service, "session_store", store),
            patch.object(
                dialog_service,
                "prepare_stage_info",
                AsyncMock(return_value=(session, "basic_info", "system", ["确认"])),
            ),
            patch.object(
                dialog_service.llm_service,
                "chat_complete",
                AsyncMock(return_value='{"reply":"请告诉我你的姓名。","complete":true}'),
            ),
        ):
            result = await dialog_service.chat_response(
                "test-session", "市场运营", "我想做市场运营", 1, "user-1"
            )

        self.assertEqual(result["reply"], "请告诉我你的姓名。")
        self.assertTrue(result["complete"])
        self.assertEqual(session["messages"][-1]["content"], "请告诉我你的姓名。")

    async def test_invalid_json_is_repaired_before_returning(self):
        session = self.make_session()
        store = FakeSessionStore(session)
        complete = AsyncMock(side_effect=[
            "请告诉我你的姓名",
            '{"reply":"请告诉我你的姓名。","complete":true}',
        ])
        with (
            patch.object(dialog_service, "session_store", store),
            patch.object(
                dialog_service,
                "prepare_stage_info",
                AsyncMock(return_value=(session, "basic_info", "system", [])),
            ),
            patch.object(dialog_service.llm_service, "chat_complete", complete),
        ):
            result = await dialog_service.chat_response(
                "test-session", "市场运营", "我想做市场运营", 1, "user-1"
            )

        self.assertEqual(result["reply"], "请告诉我你的姓名。")
        self.assertEqual(complete.await_count, 2)

    def test_parser_rejects_incomplete_envelope(self):
        with self.assertRaises(ValueError):
            dialog_service._parse_chat_response(
                '{"reply":"请告诉我你的姓名","complete":false}'
            )

    def test_parser_allows_provider_metadata_fields(self):
        raw = '{"reply":"请告诉我你的姓名。","complete":true,"usage":{"output_tokens":12}}'

        self.assertEqual(
            dialog_service._parse_chat_response(raw),
            "请告诉我你的姓名。",
        )

    def test_parser_wraps_complete_plain_text_for_compatibility(self):
        self.assertEqual(
            dialog_service._parse_chat_response("请告诉我你的姓名。"),
            "请告诉我你的姓名。",
        )

    def test_openai_finish_reason_is_detected(self):
        reason = llm_service._extract_stop_reason({
            "choices": [{"finish_reason": "length"}],
        })

        self.assertEqual(reason, "length")
        self.assertTrue(llm_service._is_length_stop(reason))


if __name__ == "__main__":
    unittest.main()
