"""全国省市级职位筛选目录，数据来自项目内 BOSS 城市码表。"""
from functools import lru_cache
import json
from pathlib import Path


CITY_CODES_PATH = (
    Path(__file__).resolve().parents[2]
    / "vendor"
    / "boss-zhipin-scraper"
    / "data"
    / "city_codes.json"
)

PROVINCES = [
    ("10101", "北京市"),
    ("10102", "上海市"),
    ("10103", "天津市"),
    ("10104", "重庆市"),
    ("10105", "黑龙江省"),
    ("10106", "吉林省"),
    ("10107", "辽宁省"),
    ("10108", "内蒙古自治区"),
    ("10109", "河北省"),
    ("10110", "山西省"),
    ("10111", "陕西省"),
    ("10112", "山东省"),
    ("10113", "新疆维吾尔自治区"),
    ("10114", "西藏自治区"),
    ("10115", "青海省"),
    ("10116", "甘肃省"),
    ("10117", "宁夏回族自治区"),
    ("10118", "河南省"),
    ("10119", "江苏省"),
    ("10120", "湖北省"),
    ("10121", "浙江省"),
    ("10122", "安徽省"),
    ("10123", "福建省"),
    ("10124", "江西省"),
    ("10125", "湖南省"),
    ("10126", "贵州省"),
    ("10127", "四川省"),
    ("10128", "广东省"),
    ("10129", "云南省"),
    ("10130", "广西壮族自治区"),
    ("10131", "海南省"),
    ("10132", "香港特别行政区"),
    ("10133", "澳门特别行政区"),
    ("10134", "台湾省"),
]


@lru_cache(maxsize=1)
def location_catalog() -> list[dict]:
    if not CITY_CODES_PATH.is_file():
        raise RuntimeError(f"全国城市码表不存在: {CITY_CODES_PATH}")
    with CITY_CODES_PATH.open(encoding="utf-8") as handle:
        city_codes = json.load(handle)

    cities_by_prefix = {prefix: [] for prefix, _ in PROVINCES}
    for city, code in city_codes.items():
        if city == "全国":
            continue
        prefix = str(code)[:5]
        if prefix in cities_by_prefix:
            cities_by_prefix[prefix].append({"label": city, "value": city})

    return [
        {
            "label": province,
            "value": province,
            "cities": cities_by_prefix[prefix],
        }
        for prefix, province in PROVINCES
    ]


def cities_for_provinces(provinces: list[str]) -> list[str]:
    selected = set(provinces)
    return [
        city["value"]
        for province in location_catalog()
        if province["value"] in selected
        for city in province["cities"]
    ]
