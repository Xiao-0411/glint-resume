"""
评分算法基准测试

目的不是断言精确分数(权重会调),而是锁住三件事:
1. 单调性 —— 强简历 > 中等 > 弱 > 空白,任何调参都不能破坏这个顺序
2. 零分锚定 —— 空白简历必须接近 0,不能再出现"空简历 62 分"
3. 已知误判 —— 曾经踩过的坑(Python3 算量化、中文岗位切词失败)不能回归

运行: python -m unittest tests.test_evaluation_scoring -v
"""
import asyncio
import unittest
from unittest.mock import patch

from app.services import evaluation_service as ev
from app.services.scoring_rules import (
    score_bullet_credibility,
    score_bullet_professional,
    score_bullet_quant,
    tokenize_job,
)


# ============ 测试夹具 ============

EMPTY_RESUME = {}

WEAK_RESUME = {
    "basic": {"fullname": "张三", "target_job": "Java后端开发工程师"},
    "education": [{"school": "某大学", "major": "计算机", "degree": "本科"}],
    "experiences": [
        {
            "id": "exp_001",
            "title": "课程项目",
            "bullets": [
                "我做了一个网站",
                "参与了团队的开发工作",
                "显著提升了系统性能",
            ],
        }
    ],
    "skills": {"technical": []},
}

STRONG_RESUME = {
    "basic": {
        "fullname": "李四",
        "target_job": "Java后端开发工程师",
        "phone": "13800000000",
        "email": "a@b.com",
    },
    "education": [{"school": "某大学", "major": "软件工程", "degree": "本科"}],
    "experiences": [
        {
            "id": "exp_001",
            "title": "电商订单系统",
            "role": "后端开发",
            "tag": {"color": "green"},
            "bullets": [
                "主导设计订单服务的分库分表方案，将单表数据量从2000万降至200万，查询耗时降低75%",
                "构建基于Redis的缓存层，接口平均响应时间从800ms优化至120ms，支撑日均50万请求",
                "重构对账模块并补充单元测试，线上资损工单从每月12起降至0起",
            ],
        },
        {
            "id": "exp_002",
            "title": "开源贡献",
            "role": "贡献者",
            "tag": {"color": "green"},
            "bullets": [
                "为Spring生态开源项目提交6个PR，其中4个已合入主干，项目已发布至github累计320 star",
                "编写Java并发工具类文档，覆盖12个核心API，被社区采纳为官方文档一部分",
            ],
        },
        {
            "id": "exp_003",
            "title": "算法竞赛",
            "role": "队长",
            "tag": {"color": "green"},
            "bullets": [
                "带领3人团队获校级程序设计竞赛第2名，在全国前5%的参赛队伍中完成全部6道题",
            ],
        },
    ],
    "skills": {
        "technical": ["Java", "Spring", "MySQL", "Redis", "Kafka", "Docker"],
        "soft": ["团队协作"],
    },
    "awards": ["校级一等奖学金"],
}

# 中等简历:有内容但量化和专业度都一般
MEDIUM_RESUME = {
    "basic": {"fullname": "王五", "target_job": "前端开发", "email": "c@d.com"},
    "education": [{"school": "某大学", "major": "计算机", "degree": "本科"}],
    "experiences": [
        {
            "id": "exp_001",
            "title": "管理系统",
            "tag": {"color": "green"},
            "bullets": [
                "负责前端页面的开发与维护，完成8个业务页面",
                "使用Vue框架实现组件化改造，提高了代码复用率",
            ],
        },
        {
            "id": "exp_002",
            "title": "社团活动",
            "tag": {"color": "yellow"},
            "bullets": ["协助组织了社团的迎新活动"],
        },
    ],
    "skills": {"technical": ["Vue", "JavaScript", "CSS"]},
}


def _evaluate(resume, target_job=""):
    """跑完整评分,LLM 部分打桩为不可用(退化为纯规则分),保证结果可复现"""
    with patch.object(ev, "_score_professionalism_llm", return_value={}) as _:
        async def run():
            return await ev.evaluate_resume(resume, target_job)
        return asyncio.run(run())


def _dim(report, name):
    for d in report["dimensions"]:
        if d["name"] == name:
            return d["score"]
    raise AssertionError(f"维度 {name} 不存在")


# ============ 分词 ============

class TestTokenizeJob(unittest.TestCase):
    """旧实现用 [\\s/、,,]+ 切中文岗位名,整串变成一个 token"""

    def test_chinese_job_splits_into_multiple_tokens(self):
        tokens = tokenize_job("Java后端开发工程师")
        self.assertIn("java", tokens)
        self.assertIn("后端", tokens)
        # 关键:不能整串成为一个 token
        self.assertNotIn("java后端开发工程师", tokens)

    def test_stopwords_removed(self):
        # "工程师" 本身没有区分度,不应计入关键词
        self.assertNotIn("工程师", tokenize_job("算法工程师"))

    def test_longest_match_wins(self):
        # "产品经理" 不应被切成 "产品"
        self.assertIn("产品经理", tokenize_job("产品经理"))

    def test_unknown_job_falls_back_to_bigram(self):
        # 词典没有的岗位也要能切出东西,不能返回空
        self.assertTrue(len(tokenize_job("量子计算研究员")) > 0)

    def test_empty(self):
        self.assertEqual(tokenize_job(""), [])


# ============ 单条 bullet 打分 ============

class TestBulletQuant(unittest.TestCase):
    def test_no_false_positive_on_version_number(self):
        # 曾经的 bug:单位可选,导致 "Python3" 被当作量化
        self.assertEqual(score_bullet_quant("使用Python3开发"), 0.0)

    def test_no_false_positive_on_ordinal_group(self):
        # "第2组" 是编号不是成果
        self.assertEqual(score_bullet_quant("担任第2组组长"), 0.0)

    def test_delta_quant_scores_highest(self):
        s = score_bullet_quant("将响应时间从800ms降低到120ms，提升85%")
        self.assertGreaterEqual(s, 0.9)

    def test_plain_quant_middling(self):
        s = score_bullet_quant("服务5万用户")
        self.assertTrue(0.5 <= s <= 0.8, f"got {s}")

    def test_vague_words_penalized(self):
        self.assertEqual(score_bullet_quant("显著提升了系统性能"), 0.0)

    def test_vague_drags_down_real_quant(self):
        # 有真数字但也有模糊词,应低于纯数字版本
        with_vague = score_bullet_quant("显著提升，覆盖3个模块")
        without = score_bullet_quant("覆盖3个模块")
        self.assertLess(with_vague, without)


class TestBulletProfessional(unittest.TestCase):
    def test_strong_verb_lead_scores_high(self):
        s = score_bullet_professional(
            "主导设计后端服务架构，落地12个核心接口，支撑日均10万请求"
        )
        self.assertGreaterEqual(s, 0.7)

    def test_first_person_penalized(self):
        self.assertLess(score_bullet_professional("我做了一个网站"), 0.2)

    def test_too_short_gets_near_zero(self):
        # 旧实现里裸 "优化" 二字也能命中动词库
        self.assertLessEqual(score_bullet_professional("优化"), 0.1)

    def test_verb_must_lead_to_get_full_credit(self):
        lead = score_bullet_professional(
            "主导重构了核心链路，覆盖8个模块，缺陷率下降40%"
        )
        buried = score_bullet_professional(
            "这个项目里面有一些需要优化的地方后来也都处理掉了还行"
        )
        self.assertGreater(lead, buried)


class TestBulletCredibility(unittest.TestCase):
    def test_verifiable_signal_adds(self):
        self.assertGreater(
            score_bullet_credibility("项目已发布至github，累计120 star"), 0.5
        )

    def test_exaggeration_subtracts(self):
        self.assertLess(
            score_bullet_credibility("实现了行业领先的完美解决方案"), 0
        )


# ============ 维度与总分 ============

class TestDimensionScores(unittest.TestCase):
    def test_empty_resume_scores_near_zero(self):
        """核心回归:旧算法下空白简历拿 62 分「合格」"""
        report = _evaluate(EMPTY_RESUME)
        self.assertLessEqual(
            report["total_score"], 10,
            f"空白简历不应有分,实际 {report['total_score']}"
        )
        self.assertEqual(report["grade"], "待提升")

    def test_empty_resume_every_dimension_zero(self):
        report = _evaluate(EMPTY_RESUME)
        for d in report["dimensions"]:
            self.assertLessEqual(
                d["score"], 10, f"{d['name']} 在空简历下为 {d['score']}"
            )

    def test_monotonic_ordering(self):
        """强 > 中 > 弱 > 空,这是评分算法的根本要求"""
        empty = _evaluate(EMPTY_RESUME)["total_score"]
        weak = _evaluate(WEAK_RESUME, "Java后端开发工程师")["total_score"]
        medium = _evaluate(MEDIUM_RESUME, "前端开发")["total_score"]
        strong = _evaluate(STRONG_RESUME, "Java后端开发工程师")["total_score"]
        self.assertLess(empty, weak, f"empty={empty} weak={weak}")
        self.assertLess(weak, medium, f"weak={weak} medium={medium}")
        self.assertLess(medium, strong, f"medium={medium} strong={strong}")

    def test_dynamic_range_is_wide(self):
        """旧算法区间被压缩在 62~100(38 分),新算法要能拉开"""
        empty = _evaluate(EMPTY_RESUME)["total_score"]
        strong = _evaluate(STRONG_RESUME, "Java后端开发工程师")["total_score"]
        self.assertGreater(strong - empty, 55, f"区分度不足: {empty} → {strong}")

    def test_strong_resume_is_actually_good(self):
        """好简历不能被误伤 —— 严厉不等于一律低分"""
        report = _evaluate(STRONG_RESUME, "Java后端开发工程师")
        self.assertGreaterEqual(report["total_score"], 65,
                                f"强简历只拿到 {report['total_score']}")

    def test_match_dimension_responds_to_job(self):
        """旧实现下匹配度几乎恒定,换岗位不变分"""
        aligned = _dim(_evaluate(STRONG_RESUME, "Java后端开发工程师"), "匹配度")
        mismatched = _dim(_evaluate(STRONG_RESUME, "平面设计师"), "匹配度")
        self.assertGreater(aligned, mismatched,
                           f"对口={aligned} 不对口={mismatched}")

    def test_no_target_job_falls_back_to_resume_field(self):
        # 传空串时应回退到 basic.target_job,而不是判定为"无目标岗位"
        self.assertGreater(_dim(_evaluate(STRONG_RESUME, ""), "匹配度"), 0)

    def test_truly_no_target_job_scores_zero_match(self):
        no_job = dict(STRONG_RESUME, basic={"fullname": "李四"})
        self.assertEqual(_dim(_evaluate(no_job, ""), "匹配度"), 0)

    def test_credibility_rewards_verifiable_content(self):
        """可信度应是双向的:旧实现只扣分,好内容也拿不到高分"""
        strong = _dim(_evaluate(STRONG_RESUME), "可信度")
        weak = _dim(_evaluate(WEAK_RESUME), "可信度")
        self.assertGreater(strong, weak)
        self.assertGreater(strong, 70, "有 github/数字佐证的简历可信度应高于基准")

    def test_completeness_scales_with_experience_count(self):
        one = _score_completeness_of(1)
        three = _score_completeness_of(3)
        five = _score_completeness_of(5)
        self.assertLess(one, three)
        self.assertLess(three, five)


def _score_completeness_of(n_exp):
    resume = {
        "basic": {"fullname": "x", "phone": "1"},
        "education": [{"school": "s"}],
        "experiences": [
            {"id": f"exp_{i}", "bullets": ["主导完成了某个模块的开发工作，覆盖3个场景"]}
            for i in range(n_exp)
        ],
        "skills": {"technical": ["a", "b"]},
    }
    return ev._score_completeness(resume)["score"]


class TestLLMFallback(unittest.TestCase):
    def test_llm_failure_degrades_to_rule_score(self):
        """LLM 挂掉时不应给固定兜底分,否则所有简历专业度趋同"""
        strong = _dim(_evaluate(STRONG_RESUME), "专业度")
        weak = _dim(_evaluate(WEAK_RESUME), "专业度")
        self.assertGreater(strong, weak,
                           "LLM 不可用时专业度仍应能区分好坏简历")

    def test_report_shape_unchanged(self):
        """前端依赖这些字段,不能改结构"""
        report = _evaluate(STRONG_RESUME, "Java后端开发工程师")
        for key in ("total_score", "grade", "grade_color", "dimensions",
                    "highlights", "improvements", "action_guide",
                    "integrity_statement"):
            self.assertIn(key, report)
        self.assertEqual(len(report["dimensions"]), 5)
        self.assertEqual(len(report["highlights"]), 2)
        for imp in report["improvements"]:
            for key in ("title", "score", "desc", "target_exp_id",
                        "evidence", "actions"):
                self.assertIn(key, imp)


if __name__ == "__main__":
    unittest.main()
