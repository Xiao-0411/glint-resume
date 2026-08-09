import unittest
from unittest.mock import patch

from app.services import dialog_service


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


if __name__ == "__main__":
    unittest.main()
