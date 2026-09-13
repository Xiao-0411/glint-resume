import json
import unittest
from unittest.mock import AsyncMock, patch

from app.mock import fallback
from app.services import dialog_service, llm_service, pdf_service
from app.services import resume_sections as sections


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
        self.session.setdefault("progress", {})

    def get_or_create(self, session_id, target_job="", user_id=None):
        return self.session

    def append_message(self, session_id, role, content):
        self.session["messages"].append({"role": role, "content": content})

    def set_stage(self, session_id, stage):
        self.session["stage"] = stage

    def update_extracted(self, session_id, info):
        self.session.setdefault("extracted", {}).update(info)

    def update_progress(self, session_id, progress):
        self.session["progress"] = dict(progress)

    def get(self, session_id):
        return self.session


def make_plan(session, stage, quick=None):
    return dialog_service.TurnPlan(
        session=session,
        stage=stage,
        system_prompt="system",
        quick_replies=list(quick or []),
        progress=sections.normalize_progress(session.get("progress")),
    )


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
    def make_session(self, extracted, stage="experience_mining", progress=None):
        return {
            "session_id": "test-session",
            "target_job": "产品经理",
            "messages": [{
                "role": "assistant",
                "content": "以上是这段经历的总结，是否准确？如无误请回复确认。",
            }],
            "stage": stage,
            "extracted": extracted,
            "progress": progress or {},
        }

    async def prepare(self, session, message, section=None, user_msg_count=3):
        store = FakeSessionStore(session)
        with patch.object(dialog_service, "session_store", store):
            return await dialog_service.plan_turn(
                "test-session",
                "产品经理",
                message,
                user_msg_count=user_msg_count,
                user_id="user-1",
                section=section,
            )

    async def test_first_turn_lists_sections_and_lets_user_choose(self):
        session = self.make_session({}, stage="basic_info")
        session["messages"] = []

        plan = await self.prepare(session, "我想做产品经理", user_msg_count=1)

        self.assertEqual(plan.stage, sections.HUB_STAGE)
        self.assertIsNotNone(plan.canned_reply)
        for label in ("基本信息", "教育背景", "项目经历", "专业技能", "获奖荣誉", "自我评价"):
            self.assertIn(label, plan.canned_reply)
            self.assertIn(label, plan.quick_replies)
        self.assertNotIn(sections.GENERATE_LABEL, plan.quick_replies)
        self.assertIn("你想先从哪一块开始", plan.canned_reply)

    async def test_explicit_section_choice_enters_that_section(self):
        session = self.make_session({}, stage=sections.HUB_STAGE)
        session["messages"][-1]["content"] = sections.build_overview_reply("产品经理")

        plan = await self.prepare(session, "教育背景", section="education")

        self.assertEqual(plan.stage, "education")
        self.assertIsNone(plan.canned_reply)
        self.assertIn("用户刚刚选择了「教育背景」板块", plan.system_prompt)
        self.assertIn("确认", plan.quick_replies)

    async def test_hub_free_text_is_routed_by_keywords(self):
        session = self.make_session({}, stage=sections.HUB_STAGE)
        session["messages"][-1]["content"] = sections.build_overview_reply("产品经理")

        plan = await self.prepare(session, "我是某大学计算机专业本科，2025 年毕业")

        self.assertEqual(plan.stage, "education")
        self.assertIn("已经提供了一部分信息", plan.system_prompt)

    async def test_hub_question_falls_back_to_llm_hub_hint(self):
        session = self.make_session({}, stage=sections.HUB_STAGE)
        session["messages"][-1]["content"] = sections.build_overview_reply("产品经理")

        with patch.object(dialog_service, "_classify_section_llm", AsyncMock(return_value=None)):
            plan = await self.prepare(session, "STAR-L 是什么意思？")

        self.assertEqual(plan.stage, sections.HUB_STAGE)
        self.assertIsNone(plan.canned_reply)
        self.assertIn("剩余板块", plan.system_prompt)
        self.assertIn("教育背景", plan.quick_replies)

    async def test_incomplete_experience_blocks_confirmation(self):
        session = self.make_session({
            "experiences": [{
                "title": "课程项目",
                "role": "组员",
                "period": "2025",
                "star_l": {"situation": "课程要求"},
            }]
        })

        plan = await self.prepare(session, "确认")

        self.assertEqual(plan.stage, "experience_mining")
        self.assertIn("系统质量门槛", plan.system_prompt)
        self.assertIn("结果或成果证据", plan.system_prompt)
        self.assertIn("我补充具体行动", plan.quick_replies)

    async def test_confirmed_experience_asks_for_another(self):
        session = self.make_session({"experiences": [complete_experience()]})

        plan = await self.prepare(session, "确认")

        self.assertEqual(plan.stage, "experience_mining")
        self.assertIn("当前经历已确认", plan.system_prompt)
        self.assertIn("没有其他经历了", plan.quick_replies)

    async def test_no_more_experience_completes_section_and_returns_to_hub(self):
        session = self.make_session({"experiences": [complete_experience()]})
        session["messages"][-1]["content"] = "这段经历已确认。还有其他经历要补充吗？"

        plan = await self.prepare(session, "没有其他经历了")

        self.assertEqual(plan.stage, sections.HUB_STAGE)
        self.assertIn("experience_mining", plan.progress["completed"])
        self.assertIn("「项目经历」已完成", plan.canned_reply)
        self.assertIn("还剩下这些板块", plan.canned_reply)
        self.assertNotIn("项目经历", plan.quick_replies)
        self.assertIn("基本信息", plan.quick_replies)
        # 必填的基本信息还没做,不能生成
        self.assertNotIn(sections.GENERATE_LABEL, plan.quick_replies)
        self.assertEqual(session["stage"], sections.HUB_STAGE)
        self.assertEqual(session["progress"]["completed"], ["experience_mining"])

    async def test_force_advance_without_data_marks_section_skipped(self):
        session = self.make_session({})

        plan = await self.prepare(session, "跳过")

        self.assertEqual(plan.stage, sections.HUB_STAGE)
        self.assertIn("experience_mining", plan.progress["skipped"])
        self.assertNotIn("experience_mining", plan.progress["completed"])
        self.assertIn("已跳过「**项目经历**」", plan.canned_reply)

    async def test_generate_is_offered_once_required_sections_are_done(self):
        session = self.make_session(
            {"experiences": [complete_experience()], "fullname": "李同学"},
            stage="skills",
            progress={"completed": ["basic_info", "experience_mining"]},
        )
        session["messages"][-1]["content"] = "- 技术栈：Python\n以上信息是否准确？如无误请回复“确认”。"
        session["extracted"]["skills"] = {"technical": ["Python"]}

        plan = await self.prepare(session, "确认")

        self.assertEqual(plan.stage, sections.HUB_STAGE)
        self.assertIn(sections.GENERATE_LABEL, plan.quick_replies)
        self.assertIn("必填板块都已完成", plan.canned_reply)

    async def test_generate_request_is_blocked_until_required_sections_done(self):
        session = self.make_session({}, stage=sections.HUB_STAGE, progress={"completed": ["education"]})

        plan = await self.prepare(session, "生成简历", section="generate")

        self.assertEqual(plan.stage, sections.HUB_STAGE)
        self.assertIn("生成简历前还需要先完成必填板块", plan.canned_reply)
        self.assertIn("基本信息", plan.canned_reply)
        self.assertIn("项目经历", plan.canned_reply)

    async def test_generate_request_moves_to_ready_when_allowed(self):
        session = self.make_session(
            {}, stage=sections.HUB_STAGE,
            progress={"completed": ["basic_info", "experience_mining"]},
        )

        plan = await self.prepare(session, "生成简历")

        self.assertEqual(plan.stage, sections.READY_STAGE)
        self.assertEqual(plan.quick_replies, [])
        self.assertIn("信息收集完成", plan.canned_reply)

    async def test_switch_request_inside_section_changes_section(self):
        session = self.make_session({}, stage="education")
        session["messages"][-1]["content"] = "请告诉我你的学校和专业。"

        plan = await self.prepare(session, "先做技能吧")

        self.assertEqual(plan.stage, "skills")
        self.assertIn("用户刚刚选择了「专业技能」板块", plan.system_prompt)

    async def test_revisiting_completed_section_asks_what_to_change(self):
        session = self.make_session(
            {}, stage=sections.HUB_STAGE, progress={"completed": ["education"]},
        )

        plan = await self.prepare(session, "教育背景", section="education")

        self.assertEqual(plan.stage, "education")
        self.assertIn("重新选择了已完成的「教育背景」板块", plan.system_prompt)


class ResumeSectionsTests(unittest.TestCase):
    def test_order_normalization_keeps_every_section_once(self):
        order = sections.normalize_section_order(["skills", "education", "skills", "unknown"])

        self.assertEqual(order[:2], ["skills", "education"])
        self.assertEqual(sorted(order), sorted(sections.DEFAULT_SECTION_ORDER))

    def test_education_can_be_moved_to_the_end(self):
        order = sections.normalize_section_order(
            ["experience_mining", "skills", "awards", "self_evaluation", "education"]
        )

        self.assertEqual(order[-1], "education")

    def test_hub_reply_after_last_section_offers_generation(self):
        progress = {"completed": sections.SECTION_KEYS}

        reply = sections.build_hub_reply(progress, just_finished="self_evaluation")

        self.assertIn("所有板块都已完成", reply)
        self.assertEqual(sections.hub_quick_replies(progress), [sections.GENERATE_LABEL])

    def test_hub_reply_never_looks_like_a_recap(self):
        reply = sections.build_hub_reply({}, just_finished="education")

        self.assertFalse(any(signal in reply for signal in dialog_service.RECAP_SIGNALS))

    def test_keyword_routing_requires_a_single_winner(self):
        self.assertEqual(sections.infer_section_from_message("获奖荣誉"), "awards")
        self.assertEqual(sections.infer_section_from_message("我拿过两次奖学金"), "awards")
        self.assertIsNone(sections.infer_section_from_message("你好"))

    def test_pdf_body_follows_section_order(self):
        resume = fallback.mock_resume("产品经理")
        resume["section_order"] = ["skills", "experience_mining", "awards", "self_evaluation", "education"]

        html = pdf_service.build_resume_html(resume)

        def pos(title):
            return html.index(f'<div class="section-title">{title}</div>')

        self.assertLess(pos("技能清单"), pos("项目经历"))
        self.assertLess(pos("项目经历"), pos("教育背景"))
        self.assertLess(pos("自我评价"), pos("教育背景"))


class MockDialogTests(unittest.TestCase):
    def test_mock_flow_walks_through_section_selection(self):
        session = {"messages": [], "stage": "basic_info", "progress": {}}

        first = fallback.mock_chat_reply("产品经理", 1, session=session, user_message="我想做产品经理")
        self.assertEqual(first["stage"], sections.HUB_STAGE)
        self.assertIn("教育背景", first["quick_replies"])

        session["messages"].append({"role": "assistant", "content": first["reply"]})
        session["stage"] = first["stage"]
        picked = fallback.mock_chat_reply(
            "产品经理", 2, session=session, user_message="教育背景", section="education"
        )
        self.assertEqual(picked["stage"], "education")

        session["stage"] = picked["stage"]
        done = fallback.mock_chat_reply("产品经理", 3, session=session, user_message="本科 2025 届")
        self.assertEqual(done["stage"], sections.HUB_STAGE)
        self.assertEqual(done["progress"]["completed"], ["education"])
        self.assertNotIn("教育背景", done["quick_replies"])


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
                "plan_turn",
                AsyncMock(return_value=make_plan(session, "experience_mining")),
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
                "plan_turn",
                AsyncMock(return_value=make_plan(session, "basic_info")),
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
                "plan_turn",
                AsyncMock(return_value=make_plan(session, "basic_info")),
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
                "plan_turn",
                AsyncMock(return_value=make_plan(session, "basic_info", ["确认"])),
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
                "plan_turn",
                AsyncMock(return_value=make_plan(session, "basic_info")),
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
