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
from app.services import jd_corpus
from app.services.scoring_rules import (
    score_bullet_credibility,
    score_bullet_professional,
    score_bullet_quant,
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
    """跑完整评分。

    两处打桩保证结果可复现:
    - LLM 置为不可用 → 专业度退化为纯规则分
    - JD 语料置为固定样本 → 匹配度不依赖本机数据库里有没有爬到职位,
      否则测试会随爬虫数据漂移(没有 DB 时还会每次尝试真实连接)
    """
    jd_corpus.clear_cache()
    with patch.object(ev, "_score_professionalism_llm", return_value={}), \
            patch.object(jd_corpus, "_fetch_jd_rows", side_effect=_fake_jd_rows):
        async def run():
            return await ev.evaluate_resume(resume, target_job)
        result = asyncio.run(run())
    jd_corpus.clear_cache()
    return result


class _FakeJob:
    """模拟 jobs 表的一行,只保留画像统计用到的字段"""

    def __init__(self, job_id, requirements):
        self.id = job_id
        self.title = ""
        self.requirements = requirements
        self.tags = []
        self.description = ""


# 各岗位的模拟招聘要求。测试只需要"有足够语料且要求稳定",不追求真实分布。
_FAKE_CORPUS = {
    "java": ["Java", "Spring", "MySQL", "Redis"],
    "前端": ["JavaScript", "Vue", "CSS", "HTML"],
    "设计": ["Figma", "UI设计", "交互设计"],
}


def _fake_jd_rows(db, target_job):
    low = (target_job or "").lower()
    for key, reqs in _FAKE_CORPUS.items():
        if key in low:
            return [_FakeJob(i, reqs) for i in range(6)]
    return []


def _dim(report, name):
    for d in report["dimensions"]:
        if d["name"] == name:
            return d["score"]
    raise AssertionError(f"维度 {name} 不存在")


# ============ 技能识别与岗位画像 ============

class TestSkillExtraction(unittest.TestCase):
    """技能词边界:三个爬虫曾各有一份裸正则实现,把 PostgreSQL 认成 SQL"""

    def test_no_substring_false_positive(self):
        from app.services.skill_extract import extract_skills
        found = extract_skills("掌握 PostgreSQL 与 MongoDB")
        self.assertIn("PostgreSQL", found)
        self.assertNotIn("SQL", found)

    def test_alias_normalized(self):
        from app.services.skill_extract import extract_skills
        # 简历写 k8s、JD 写 Kubernetes,必须归一才能比对上
        self.assertIn("Kubernetes", extract_skills("熟悉 k8s 容器编排"))
        self.assertIn("Go", extract_skills("使用 Golang 开发"))

    def test_strict_mode_drops_non_skills(self):
        from app.services.skill_extract import canonicalize
        # 智联的 tags 放的是福利,不能当成技能要求
        welfare = ["五险一金", "带薪年假", "Java"]
        self.assertEqual(canonicalize(welfare, strict=True), ["Java"])
        # 简历侧要保留词表外的真实技能
        self.assertIn("自研调度框架", canonicalize(["自研调度框架"]))


class TestJobProfile(unittest.TestCase):
    """岗位画像必须来自真实 JD 的文档频率,而不是手写词表"""

    def test_weight_reflects_document_frequency(self):
        jd_corpus.clear_cache()
        rows = [_FakeJob(i, ["Java", "MySQL"]) for i in range(9)]
        rows.append(_FakeJob(9, ["Java", "Flink"]))
        with patch.object(jd_corpus, "_fetch_jd_rows", return_value=rows):
            profile = jd_corpus.build_profile(object(), "Java后端开发工程师")
        jd_corpus.clear_cache()
        self.assertEqual(profile.source, "jd")
        # 10 条里 9 条要 MySQL、1 条要 Flink
        self.assertGreater(profile.weight_of("MySQL"), profile.weight_of("Flink"))

    def test_degrades_when_corpus_too_small(self):
        jd_corpus.clear_cache()
        with patch.object(jd_corpus, "_fetch_jd_rows", return_value=[]):
            profile = jd_corpus.build_profile(object(), "Java后端开发工程师")
        jd_corpus.clear_cache()
        self.assertEqual(profile.source, "starter")

    def test_single_char_terms_dropped(self):
        # "的" 会 LIKE '%的%' 命中几乎所有 JD,污染统计
        self.assertEqual(jd_corpus._job_search_terms("的"), [])

    def test_like_wildcards_escaped(self):
        self.assertEqual(jd_corpus._like_pattern("100%"), "%100\\%%")


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

    def test_whitespace_does_not_break_delta_quant(self):
        """回归:曾把 \\s 当断句,"降低 65%" 比 "降低65%" 低 48 分,
        而带空格恰恰是更规范的排版"""
        self.assertEqual(
            score_bullet_quant("接口耗时降低 65%"),
            score_bullet_quant("接口耗时降低65%"),
        )

    def test_space_separated_clauses_not_treated_as_delta(self):
        """但空格也不能一律放行:跨词拼接不是成果量化"""
        self.assertLess(score_bullet_quant("提升 团队协作 参与3次评审"), 0.9)

    def test_before_after_range_recognized(self):
        """"从 A 到 B" 是最有说服力的写法,两端未必都带量纲"""
        self.assertGreaterEqual(score_bullet_quant("QPS 从 200 提升至 1200"), 0.9)
        self.assertGreaterEqual(score_bullet_quant("单表数据量从2000万降至200万"), 0.9)

    def test_date_range_is_not_an_achievement(self):
        """回归:任职时间区间曾被当成成果量化"""
        self.assertLess(score_bullet_quant("从2019年到2021年担任第2组组长"), 0.9)

    def test_long_input_does_not_hang(self):
        """回归:\\d+\\.?\\d* 的歧义量词对长数字串有指数级回溯"""
        import time
        evil = "从" + "1" * 2000 + "提升" + "9" * 2000
        start = time.monotonic()
        score_bullet_quant(evil)
        self.assertLess(time.monotonic() - start, 0.5)


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

    def test_empty_rhetoric_cannot_game_professionalism(self):
        """回归:只看开头动词和字数时,纯堆砌形容词的句子能拿 0.80"""
        padded = score_bullet_professional(
            "主导设计行业领先的完美架构，显著提升性能，大幅优化体验，极大降低成本"
        )
        substantive = score_bullet_professional(
            "主导设计后端服务架构，落地12个核心接口，支撑日均10万请求"
        )
        self.assertLess(padded, substantive)
        self.assertLess(padded, 0.3, f"空话句仍拿到 {padded}")


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

    def test_keyword_stuffing_does_not_beat_real_skills(self):
        """核心回归:匹配度必须衡量"会不会这个岗位要的技能",
        而不是"简历里出现了几次岗位名"。

        曾经的冷启动兜底按岗位名关键词覆盖度打分,结果反复写"量子炼金"
        的空洞简历拿 92 分,而有真实成果的简历拿 0 分。"""
        stuffer = {
            "basic": {"fullname": "刷分", "target_job": "Java后端开发工程师"},
            "education": [{"school": "某大学"}],
            "experiences": [{
                "id": "exp_001", "title": "Java后端", "role": "Java后端开发",
                "tag": {"color": "green"},
                "bullets": ["负责Java后端相关工作，参与Java后端开发，熟悉Java后端流程"],
            }],
            "skills": {"technical": []},
        }
        stuffed = _dim(_evaluate(stuffer, "Java后端开发工程师"), "匹配度")
        real = _dim(_evaluate(STRONG_RESUME, "Java后端开发工程师"), "匹配度")
        self.assertGreater(real, stuffed,
                           f"真材实料={real} 蹭关键词={stuffed}")

    def test_unknown_job_reports_no_data_instead_of_guessing(self):
        """语料覆盖不到的岗位应如实说明,而不是编一个分数"""
        resume = dict(STRONG_RESUME, basic={"fullname": "李四", "target_job": "量子炼金术士"})
        report = _evaluate(resume, "量子炼金术士")
        match = next(d for d in report["dimensions"] if d["name"] == "匹配度")
        self.assertEqual(match["score"], 0)
        self.assertIn("暂无", match["desc"])

    def test_proven_skills_outrank_merely_listed(self):
        """写进经历(真的用过)应比只列在技能栏得分高 —— 打分要与内容挂钩"""
        listed_only = {
            "basic": {"fullname": "A", "target_job": "Java后端开发工程师"},
            "education": [{"school": "某大学"}],
            "experiences": [{"id": "e1", "tag": {"color": "green"},
                             "bullets": ["参与了一些开发工作"]}],
            "skills": {"technical": ["Java", "Spring", "MySQL", "Redis"]},
        }
        proven = {
            "basic": {"fullname": "B", "target_job": "Java后端开发工程师"},
            "education": [{"school": "某大学"}],
            "experiences": [{"id": "e1", "tag": {"color": "green"}, "bullets": [
                "主导设计订单服务，基于Java与Spring落地，MySQL分库分表配合Redis缓存",
            ]}],
            "skills": {"technical": ["Java", "Spring", "MySQL", "Redis"]},
        }
        self.assertGreater(
            _dim(_evaluate(proven, "Java后端开发工程师"), "匹配度"),
            _dim(_evaluate(listed_only, "Java后端开发工程师"), "匹配度"),
        )


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
