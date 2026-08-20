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
    assert exact["score"] >= 85 and exact["level"] == "green"

    # 技能清单更详细不应该拉低分数
    detailed = _calc_match("Java开发", {
        "title": "Java开发",
        "requirements": ["Java", "SpringCloud", "MySQL", "Redis", "ERP开发经验", "MES开发经验"],
    })
    assert detailed["score"] >= exact["score"]

    unrelated = _calc_match("Java开发", {"title": "UI设计师", "requirements": []})
    assert unrelated["level"] == "red"


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
