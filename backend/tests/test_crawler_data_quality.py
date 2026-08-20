"""爬虫数据清洗与匹配打分的回归测试。

覆盖三类曾经导致脏数据或错误展示的缺陷：
1. 城市提取只认 12 个硬编码城市，其余 361 个城市的岗位被静默丢弃；
2. 岗位名以【】角标开头时被截断成空串；
3. 匹配度用固定技能表除以岗位技能数，技能越详细分数越低。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api.jobs import _calc_match, _clean_title  # noqa: E402
from app.crawlers.card_parser import (  # noqa: E402
    clean_title,
    is_publishable,
    parse_company,
    parse_education,
    parse_experience,
    parse_salary,
)
from app.crawlers.cursor import slice_at  # noqa: E402
from app.services.location_catalog import (  # noqa: E402
    all_city_names,
    city_of,
    extract_location,
    matches_city,
)


def test_city_catalog_covers_whole_country():
    names = all_city_names()
    assert len(names) > 300
    # 曾经被硬编码正则漏掉的城市
    for city in ("厦门", "长沙", "齐齐哈尔", "乌鲁木齐", "三亚", "呼和浩特"):
        assert city in names


def test_extract_location_beyond_hardcoded_cities():
    assert extract_location("高级Java开发 厦门-思明区 20-30k 本科") == "厦门-思明区"
    assert extract_location("运维工程师 齐齐哈尔-建华区 8-12k") == "齐齐哈尔-建华区"
    assert extract_location("数据分析 乌鲁木齐 10-15k") == "乌鲁木齐"
    assert extract_location("完全没有城市名的文本") == ""


def test_city_of_and_matches_city():
    assert city_of("上海·徐汇区·漕河泾") == "上海"
    assert city_of("厦门-思明区") == "厦门"
    assert matches_city("厦门-思明区", "厦门")
    assert not matches_city("北京-海淀区", "厦门")


def test_clean_title_keeps_text_after_leading_badge():
    # 曾经按【切分，导致以角标开头的岗位名变成空串
    assert clean_title("【Python】后端开发工程师") == "后端开发工程师"
    assert _clean_title("【27届校招提前批】数据分析岗") == "数据分析岗"
    assert _clean_title("Java开发工程师 15-25k") == "Java开发工程师"
    assert _clean_title("产品经理") == "产品经理"


def test_card_parser_extracts_real_fields():
    text = "后端开发工程师 【 北京-海淀区 】 10-12k 经验不限 统招本科 北京擎靖天启科技服务有限公司 何女士·经理"
    assert parse_company(text, "后端开发工程师") == "北京擎靖天启科技服务有限公司"
    assert parse_salary(text) == "10-12k"
    assert parse_education(text) == "本科"
    assert parse_experience(text) == "经验不限"


def test_is_publishable_rejects_incomplete_cards():
    complete = {
        "title": "后端开发工程师",
        "platform_job_id": "j1",
        "company": "某某科技有限公司",
        "salary": "10-12k",
        "location": "北京-海淀区",
    }
    assert is_publishable(complete)

    # 卡片只抓到按钮文案时的典型残缺记录
    assert not is_publishable({**complete, "company": "未知公司"})
    assert not is_publishable({**complete, "salary": ""})
    assert not is_publishable({**complete, "location": ""})
    assert not is_publishable({**complete, "location": "火星基地"})


def test_cursor_slice_wraps_and_covers_pool():
    pool = [f"c{i}" for i in range(10)]
    seen = set()
    for step in range(5):
        seen.update(slice_at(pool, step * 4, 4))
    assert seen == set(pool)


def test_match_score_uses_title_not_skill_count():
    exact = _calc_match("Java开发", {"title": "Java开发", "requirements": []})
    assert exact["score"] >= 80 and exact["level"] == "green"

    # 技能清单更详细不应该拉低分数
    detailed = _calc_match("Java开发", {
        "title": "Java开发",
        "requirements": ["Java", "SpringCloud", "MySQL", "Redis", "ERP开发经验", "MES开发经验"],
    })
    assert detailed["score"] >= exact["score"]

    unrelated = _calc_match("Java开发", {"title": "UI设计师", "requirements": []})
    assert unrelated["level"] == "red"


def test_short_skill_list_does_not_penalise_matching_job():
    """JD 写得简略不代表岗位不对口。

    曾经用「命中数 ÷ 目标技能数」加权，导致只列 3 个技能的
    "Java开发工程师" 得分低于技能更全的同类岗位，甚至被判成红色。
    """
    short = _calc_match("Java开发", {
        "title": "Java开发工程师",
        "requirements": ["Java", "Maven", "Linux"],
    })
    rich = _calc_match("Java开发", {
        "title": "Java后端开发工程师",
        "requirements": ["Java", "Spring Boot", "MySQL", "Redis", "数据结构", "系统设计"],
    })
    assert short["level"] == "green", f"对口岗位不应因技能少被降级: {short}"
    assert rich["level"] == "green"


def test_jd_backfill_improves_score_over_missing_detail():
    """补全 JD 后的分数应不低于仅有岗位名时。"""
    without_jd = _calc_match("Java开发", {"title": "Java开发工程师", "requirements": []})
    with_jd = _calc_match("Java开发", {
        "title": "Java开发工程师",
        "requirements": ["Java", "Spring Boot", "MySQL"],
    })
    assert with_jd["score"] >= without_jd["score"]
    assert "依据有限" in without_jd["reasons"]


def test_classifier_normalizes_invalid_values():
    from app.services.job_classifier import _normalize

    # 模型自创类目/职级时必须回落到安全默认，不能污染库
    result = _normalize({"category": "自创类目", "level": "资深", "skills": "Java, Spring", "industry": ""})
    assert result["category"] == "其他"
    assert result["level"] == "不限"
    assert result["skills"] == ["Java", "Spring"]
    assert result["industry"] == "通用"


def test_classifier_filters_recruitment_pitch_from_skills():
    """招聘话术不能进 skills。

    首批实跑中模型把"高底薪高提成，无外呼""定期团建，退役军人"这类卖点
    当成技能写进 requirements，而 requirements 直接参与匹配度打分。
    """
    from app.services.job_classifier import _normalize

    polluted = [
        "无经验应届生，实习生", "可带团队，上海九亭", "高底薪高提成，无外呼",
        "稳定全职，快速晋升", "定期团建，退役军人",
        "需求分析", "产品设计", "原型设计",
    ]
    result = _normalize({"category": "产品经理", "level": "初级", "skills": polluted, "industry": "通用"})
    assert result["skills"] == ["需求分析", "产品设计", "原型设计"]


def test_classifier_keeps_genuine_skills():
    """噪声过滤不能误杀真实技能。"""
    from app.services.job_classifier import _looks_like_noise

    for skill in ("Java", "Spring Boot", "MySQL", "需求分析", "用户研究", "Axure", "C++", "财务报表"):
        assert not _looks_like_noise(skill), f"真实技能被误判为噪声: {skill}"

    for noise in ("五险一金", "双休不加班", "高底薪高提成，无外呼", "计算机相关专业"):
        assert _looks_like_noise(noise), f"招聘话术未被拦截: {noise}"


def test_long_english_tech_names_survive_filter():
    """英文技术栈常超过中文技能的长度上限，不能按同一阈值裁掉。

    首次实现用统一的 12 字上限，把 Elasticsearch(13)、Kubernetes 等
    误判成噪声，dry-run 显示会波及 126 条记录。
    """
    from app.services.job_classifier import _looks_like_noise

    for skill in (
        "Elasticsearch", "Kubernetes", "PostgreSQL", "TypeScript",
        "React Native", "Google Cloud Platform", "CI/CD",
    ):
        assert not _looks_like_noise(skill), f"英文技术栈被误杀: {skill}"

    # 中文侧仍收紧，整句卖点必须拦住
    assert _looks_like_noise("稳定全职快速晋升定期团建")


def test_classifier_dedupes_skills():
    from app.services.job_classifier import _normalize

    result = _normalize({
        "category": "后端开发", "level": "中级", "industry": "金融",
        "skills": ["Java", "java", "JAVA", "Spring"],
    })
    assert result["skills"] == ["Java", "Spring"]


def test_classifier_extracts_json_from_wrapped_output():
    from app.services.job_classifier import _extract_json_array

    expected = [{"id": 0, "category": "后端开发"}]
    assert _extract_json_array('[{"id":0,"category":"后端开发"}]') == expected
    assert _extract_json_array('```json\n[{"id":0,"category":"后端开发"}]\n```') == expected
    assert _extract_json_array('结果：[{"id":0,"category":"后端开发"}] 完毕') == expected


def test_classifier_merges_skills_into_requirements():
    from app.services.job_classifier import apply_classification

    job = {"title": "Java后端", "requirements": ["Java", "Maven"]}
    merged = apply_classification(job, {
        "category": "后端开发", "skills": ["Java", "Redis"], "level": "中级", "industry": "电商",
    })
    assert merged["category"] == "后端开发"
    # Java 已存在不应重复
    assert merged["requirements"] == ["Java", "Maven", "Redis"]


def test_job_catalog_covers_more_than_legacy_keywords():
    from app.crawlers.base import JOB_KEYWORDS
    from app.services.job_catalog import category_names

    names = category_names()
    assert len(names) > len(JOB_KEYWORDS)
    # 旧关键词表缺失的方向
    for expected in ("Go开发", "DBA", "供应链管理", "临床研究"):
        assert expected in names


def test_match_score_handles_missing_target():
    result = _calc_match("", {"title": "Java开发", "requirements": []})
    assert result["score"] == 50
    assert result["level"] == "yellow"


def _run() -> int:
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    failed = 0
    for test in tests:
        try:
            test()
            print(f"  PASS  {test.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"  FAIL  {test.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"  ERROR {test.__name__}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_run())
