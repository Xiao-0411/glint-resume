"""职位分类目录：全量抓取的遍历维度。

优先使用 data/job_categories.json（由 scripts/fetch_job_categories.py 从
BOSS 官方接口抓取）。该文件不存在时回退到内置基线表，保证抓取链路
不因为缺一次性准备步骤而中断。

内置表覆盖主流招聘方向，但**不等于平台全量**；要真正做到「按城市抓全部岗位」，
需要先跑一次 fetch_job_categories.py 拿到平台自己的类目树。
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

CATEGORIES_PATH = Path(__file__).resolve().parents[2] / "data" / "job_categories.json"

# 内置基线：按大类组织的常见岗位方向，作为官方类目树缺失时的兜底。
# 结构与官方抓取结果一致，便于无缝替换。
FALLBACK_CATEGORIES: list[dict] = [
    # 技术
    *[{"code": "", "name": name, "path": f"技术 > {name}", "top": "技术"} for name in [
        "Java开发", "Python开发", "C++开发", "C#开发", "Go开发", "PHP开发", "Node.js开发",
        "前端开发", "后端开发", "全栈工程师", "移动开发", "iOS开发", "Android开发",
        "鸿蒙开发", "小程序开发", "测试工程师", "自动化测试", "运维工程师", "SRE",
        "DBA", "网络工程师", "系统架构师", "技术经理", "算法工程师", "机器学习",
        "深度学习", "自然语言处理", "计算机视觉", "大数据开发", "数据仓库", "数据挖掘",
        "数据分析师", "BI工程师", "嵌入式开发", "硬件工程师", "芯片工程师", "驱动开发",
        "安全工程师", "渗透测试", "区块链开发", "游戏开发", "图形/引擎开发", "音视频开发",
    ]],
    # 产品
    *[{"code": "", "name": name, "path": f"产品 > {name}", "top": "产品"} for name in [
        "产品经理", "高级产品经理", "产品总监", "数据产品经理", "AI产品经理",
        "策略产品经理", "B端产品经理", "C端产品经理", "产品助理", "需求分析师",
    ]],
    # 设计
    *[{"code": "", "name": name, "path": f"设计 > {name}", "top": "设计"} for name in [
        "UI设计师", "UX设计师", "交互设计师", "视觉设计师", "平面设计师",
        "网页设计师", "游戏美术", "3D设计师", "动效设计师", "工业设计",
    ]],
    # 运营
    *[{"code": "", "name": name, "path": f"运营 > {name}", "top": "运营"} for name in [
        "产品运营", "用户运营", "内容运营", "活动运营", "社区运营", "新媒体运营",
        "电商运营", "直播运营", "社群运营", "数据运营", "游戏运营", "运营总监",
    ]],
    # 市场与销售
    *[{"code": "", "name": name, "path": f"市场销售 > {name}", "top": "市场销售"} for name in [
        "市场营销", "品牌策划", "市场推广", "SEO/SEM", "商务拓展", "销售代表",
        "销售经理", "大客户销售", "渠道销售", "电话销售", "售前顾问", "客户成功",
    ]],
    # 职能
    *[{"code": "", "name": name, "path": f"职能 > {name}", "top": "职能"} for name in [
        "人力资源", "招聘专员", "薪酬绩效", "行政专员", "财务", "会计", "审计",
        "税务", "法务", "合规", "行政经理", "总助/秘书",
    ]],
    # 供应链与制造
    *[{"code": "", "name": name, "path": f"供应链制造 > {name}", "top": "供应链制造"} for name in [
        "采购", "供应链管理", "物流", "仓储管理", "生产管理", "工艺工程师",
        "质量管理", "设备工程师", "机械工程师", "电气工程师", "结构工程师",
    ]],
    # 专业服务
    *[{"code": "", "name": name, "path": f"专业服务 > {name}", "top": "专业服务"} for name in [
        "项目经理", "项目专员", "管理咨询", "战略规划", "投资经理", "风控",
        "证券分析", "银行柜员", "保险顾问", "客服专员", "客服主管",
    ]],
    # 医疗与教育
    *[{"code": "", "name": name, "path": f"医疗教育 > {name}", "top": "医疗教育"} for name in [
        "医药代表", "临床研究", "生物工程", "药品研发", "医疗器械",
        "教师", "课程顾问", "教研", "培训讲师", "留学顾问",
    ]],
    # 其他
    *[{"code": "", "name": name, "path": f"其他 > {name}", "top": "其他"} for name in [
        "实习生", "管培生", "校园招聘", "翻译", "编辑", "记者", "摄影师",
        "建筑设计", "土木工程", "房地产", "餐饮管理", "酒店管理",
    ]],
]


@lru_cache(maxsize=1)
def _load() -> tuple[list[dict], str]:
    if CATEGORIES_PATH.is_file():
        try:
            payload = json.loads(CATEGORIES_PATH.read_text(encoding="utf-8"))
            categories = payload.get("categories") or []
            if categories:
                return categories, str(payload.get("source") or str(CATEGORIES_PATH))
        except (OSError, json.JSONDecodeError, AttributeError):
            # 码表损坏时不应中断抓取，回退到内置表。
            pass
    return FALLBACK_CATEGORIES, "builtin"


def job_categories() -> list[dict]:
    return _load()[0]


def catalog_source() -> str:
    """码表来源：官方接口 URL 或 "builtin"。用于日志与运维判断。"""
    return _load()[1]


def is_official_catalog() -> bool:
    return catalog_source() != "builtin"


def category_names() -> list[str]:
    """用于搜索的岗位词列表，保持码表顺序。"""
    seen: set[str] = set()
    names: list[str] = []
    for item in job_categories():
        name = str(item.get("name") or "").strip()
        if name and name not in seen:
            seen.add(name)
            names.append(name)
    return names
