"""
岗位适配的护栏测试

/jobs/adapt 会把 LLM 生成的文本写进用户简历,一旦放过虚构内容,
用户就会拿着一份含假信息的简历去投递。这里锁死两件事:

1. 越界必拦 —— 数字、中文数量词、名次、夸张断言、凭空添加的技能
2. 正常改写不能误伤 —— "统一身份认证""第三方登录"里的一/三不是数量,
   "测试用例"这类通用工作方法也不算可造假的资历

运行: python -m unittest tests.test_job_adapt -v
"""
import asyncio
import json
import unittest
from unittest.mock import patch

from app.services import evaluation_service as ev
from app.services import jd_corpus
from app.services import job_adapt as ja


RESUME = {
    "basic": {"fullname": "李四", "target_job": "Java后端开发工程师", "phone": "1"},
    "education": [{"school": "某大学", "major": "软件工程"}],
    "experiences": [{
        "id": "exp_001", "title": "电商订单系统", "role": "后端开发",
        "tag": {"color": "green"},
        "bullets": [
            "负责订单模块的接口开发，处理了日均5万笔订单",
            "参与数据库优化工作",
        ],
    }],
    "skills": {"technical": ["Java", "Spring", "MySQL"]},
}

JOB = {
    "id": "job_db_1", "title": "Java后端开发工程师", "company": "某公司",
    "requirements": ["Java", "Spring", "MySQL", "Redis"],
    "tags": ["五险一金"],
    "description": "熟悉 Java、Spring Boot，掌握 MySQL 与 Redis。",
}

ALLOWED = {"Java", "Spring", "MySQL"}


async def _fake_score(resume, target_job):
    """真实评分引擎，但屏蔽 LLM 与 DB，保证可复现"""
    with patch.object(ev, "_score_professionalism_llm", return_value={}), \
            patch.object(jd_corpus, "_fetch_jd_rows", return_value=[]):
        return await ev.evaluate_resume(resume, target_job)


def _run(payload, resume=RESUME, job=JOB):
    async def fake_llm(**kwargs):
        return json.dumps(payload, ensure_ascii=False)
    jd_corpus.clear_cache()
    with patch.object(ja.llm_service, "chat_complete", side_effect=fake_llm):
        result = asyncio.run(ja.adapt_resume_to_job(resume, job, None, _fake_score))
    jd_corpus.clear_cache()
    return result


class TestFabricationGuard(unittest.TestCase):
    """护栏:LLM 的越界改写必须被拦下"""

    def test_blocks_arabic_number(self):
        self.assertIsNotNone(
            ja._has_invented_claim("参与数据库优化", "优化数据库，效率提升200%", ALLOWED))

    def test_blocks_chinese_quantity(self):
        for text in ("性能提升三倍", "服务数万用户", "覆盖十余个模块"):
            self.assertIsNotNone(
                ja._has_invented_claim("参与数据库优化", f"优化数据库，{text}", ALLOWED),
                f"未拦截: {text}")

    def test_blocks_rank_claim(self):
        self.assertIsNotNone(
            ja._has_invented_claim("参与竞赛", "参与竞赛，获得第一名", ALLOWED))

    def test_blocks_exaggeration(self):
        self.assertIsNotNone(
            ja._has_invented_claim("参与优化", "优化系统，大幅提升体验", ALLOWED))

    def test_blocks_skill_not_in_resume(self):
        """最危险的一类:给用户安上他不会的技术"""
        for skill in ("Redis", "Kubernetes", "Kafka"):
            self.assertIsNotNone(
                ja._has_invented_claim("参与后端开发", f"主导后端开发，引入 {skill}", ALLOWED),
                f"未拦截凭空添加的技能: {skill}")


class TestGuardFalsePositives(unittest.TestCase):
    """护栏不能误伤正常改写,否则适配功能等于不可用"""

    def test_allows_chinese_digit_inside_words(self):
        """“统一”“一致性”“第三方”里的一/三不是数量表述"""
        for text in ("主导统一身份认证模块开发",
                     "主导数据一致性校验方案落地",
                     "负责第三方登录能力接入"):
            self.assertIsNone(
                ja._has_invented_claim("负责登录模块开发", text, ALLOWED),
                f"误伤: {text}")

    def test_allows_generic_work_methods(self):
        """“测试用例”“需求分析”是做事方式,不是可造假的资历"""
        self.assertIsNone(
            ja._has_invented_claim("负责功能测试", "主导功能测试用例设计与执行", ALLOWED))

    def test_allows_reusing_original_numbers(self):
        self.assertIsNone(ja._has_invented_claim(
            "负责订单接口开发，处理日均5万笔订单",
            "主导订单接口设计与开发，支撑日均5万笔订单", ALLOWED))

    def test_allows_highlighting_owned_skills(self):
        self.assertIsNone(ja._has_invented_claim(
            "参与数据库优化", "主导 MySQL 慢查询优化", ALLOWED))


class TestBulletAddressing(unittest.TestCase):
    def test_keys_unique_without_ids(self):
        """PDF 上传的简历各段 id 常为空串,按 id 拼键会碰撞改错内容"""
        resume = {"experiences": [
            {"id": "", "bullets": ["第一段第一条", "第一段第二条"]},
            {"id": "", "bullets": ["第二段第一条"]},
        ]}
        keys = [f"{e}#{b}" for e, b, _ in ja._collect_bullets(resume)]
        self.assertEqual(len(keys), len(set(keys)))

    def test_truncation_is_exact(self):
        resume = {"experiences": [
            {"id": f"e{n}", "bullets": [f"e{n}b{i}" for i in range(10)]} for n in range(5)
        ]}
        self.assertEqual(len(ja._collect_bullets(resume)), ja.MAX_BULLETS)

    def test_blank_bullets_do_not_consume_budget(self):
        resume = {"experiences": [{"id": "e1", "bullets": ["", "  ", "有内容的一条"]}]}
        self.assertEqual(len(ja._collect_bullets(resume)), 1)


class TestAdaptFlow(unittest.TestCase):
    def test_applies_valid_rewrite_and_scores_for_real(self):
        r = _run({
            "rewrites": [{
                "id": "0#0",
                "adapted": "主导订单服务接口设计与开发，基于 Java 与 Spring 支撑日均5万笔订单",
                "reason": "突出岗位要求的技术栈",
            }],
            "summary": ["突出 Java/Spring"], "skill_advice": "建议补充 Redis",
        })
        self.assertTrue(r["adapted"])
        self.assertEqual(len(r["appliedRewrites"]), 1)
        # 分数来自真实评分引擎,不是常量
        self.assertIsInstance(r["originalScore"], int)
        self.assertIsInstance(r["adaptedScore"], int)
        # 原简历不能被改动
        self.assertEqual(RESUME["experiences"][0]["bullets"][0],
                         "负责订单模块的接口开发，处理了日均5万笔订单")

    def test_rejected_rewrite_keeps_original_and_says_why(self):
        r = _run({
            "rewrites": [{"id": "0#1", "adapted": "优化数据库，性能提升300%", "reason": "加数据"}],
            "summary": ["优化表述"], "skill_advice": "",
        })
        self.assertFalse(r["adapted"])
        self.assertEqual(r["adaptedResume"]["experiences"][0]["bullets"][1], "参与数据库优化工作")
        # 不能说成"简历无需调整" —— 真实原因是改写被拒
        self.assertIn("拒绝", r["changes"][0])

    def test_empty_rewrites_reports_already_aligned(self):
        r = _run({"rewrites": [], "summary": [], "skill_advice": ""})
        self.assertTrue(r["noChange"])
        self.assertEqual(r["originalScore"], r["adaptedScore"])
        self.assertIn("无需调整", r["changes"][0])

    def test_fabricated_bullet_id_ignored(self):
        r = _run({
            "rewrites": [{"id": "9#0", "adapted": "一段用户没有的经历", "reason": "x"}],
            "summary": [], "skill_advice": "",
        })
        all_bullets = [b for e in r["adaptedResume"]["experiences"] for b in e["bullets"]]
        self.assertNotIn("一段用户没有的经历", all_bullets)

    def test_missing_resume_or_job_raises(self):
        for resume, job in ((None, JOB), ({"experiences": []}, JOB), (RESUME, None)):
            with self.assertRaises(ja.AdaptError):
                asyncio.run(ja.adapt_resume_to_job(resume, job, None, _fake_score))

    def test_non_dict_llm_output_becomes_llm_error(self):
        """json.loads 对 '["x"]' / '42' 都成功,但后续 .get 会 500"""
        for bad in ('["no changes"]', '42', '"none"', 'null'):
            async def fake_llm(**kwargs):
                return bad
            with patch.object(ja.llm_service, "chat_complete", side_effect=fake_llm):
                with self.assertRaises(ja.llm_service.LLMError):
                    asyncio.run(ja.adapt_resume_to_job(RESUME, JOB, None, _fake_score))

    def test_diff_sections_shape(self):
        """前端 diff 渲染依赖这个结构"""
        r = _run({
            "rewrites": [{"id": "0#0", "adapted": "主导订单模块接口开发，支撑日均5万笔订单", "reason": "x"}],
            "summary": ["x"], "skill_advice": "",
        })
        names = [s["name"] for s in r["sections"]]
        self.assertIn("项目经历", names)
        for sec in r["sections"]:
            for ch in sec["changes"]:
                self.assertIn(ch["type"], ("unchanged", "changed", "added"))
                if ch["type"] == "changed":
                    self.assertIn("original", ch)
                    self.assertIn("adapted", ch)
                else:
                    self.assertIn("text", ch)

    def test_duplicate_bullet_text_marks_only_the_changed_one(self):
        """同段内两条相同 bullet 时,按文本匹配会把没动的那条也标成已改"""
        resume = {
            "basic": {"target_job": "Java后端开发工程师"},
            "education": [{"school": "某大学"}],
            "experiences": [{
                "id": "e1", "title": "项目", "tag": {"color": "green"},
                "bullets": ["负责接口开发", "负责文档编写", "负责接口开发"],
            }],
            "skills": {"technical": ["Java"]},
        }
        r = _run({
            "rewrites": [{"id": "0#0", "adapted": "主导核心接口设计与开发", "reason": "x"}],
            "summary": ["x"], "skill_advice": "",
        }, resume=resume)
        exp_sec = next(s for s in r["sections"] if s["name"] == "项目经历")
        changed = [c for c in exp_sec["changes"] if c["type"] == "changed"]
        self.assertEqual(len(changed), 1, "重复文本导致标错行数")


if __name__ == "__main__":
    unittest.main()
