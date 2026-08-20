"""抓取 BOSS 直聘的官方职位分类树，落地为本地码表。

全量抓取按「城市 × 职位分类」遍历，分类维度必须来自平台自己的体系，
而不是手写关键词列表——手写列表既不完整，也和平台的检索口径对不上。

BOSS 的分类接口返回三级结构（如 技术 > 后端开发 > Java），
搜索时用三级（叶子）节点的 code 作为 position 参数最精确。

用法：
    python scripts/fetch_job_categories.py            # 需已登录的 CDP Chrome
    python scripts/fetch_job_categories.py --show     # 只打印已有码表概况
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

OUTPUT_PATH = Path(__file__).resolve().parents[1] / "data" / "job_categories.json"

# BOSS 公开的职位分类接口。position.json 是岗位类目树，
# condition.json 里也带一份 position 结构，作为备选来源。
CATEGORY_URLS = [
    "https://www.zhipin.com/wapi/zpCommon/data/position.json",
    "https://www.zhipin.com/wapi/zpgeek/search/job/condition.json",
]


def _fetch_via_cdp(url: str) -> dict:
    """用已登录的 Chrome 打开接口地址并读取 JSON。

    分类接口是公开数据，但直接用 httpx 请求容易被风控拦；
    走浏览器则与正常访问同源同指纹。
    """
    from app.crawlers.cdp_browser import CdpBrowser

    browser = CdpBrowser()
    try:
        browser.connect()
        _, sid = browser.open_page(url, wait_seconds=3.0)
        raw = browser.evaluate(
            "(document.body && (document.body.innerText || document.body.textContent) || '').trim()",
            sid,
        )
        text = str(raw or "").strip()
        if not text:
            raise RuntimeError("页面无内容")
        return json.loads(text)
    finally:
        browser.close()


def _walk(node, path: list[str], out: list[dict]) -> None:
    """递归展开分类树，收集带 code 的叶子节点。"""
    if isinstance(node, list):
        for item in node:
            _walk(item, path, out)
        return
    if not isinstance(node, dict):
        return

    name = str(node.get("name") or node.get("label") or "").strip()
    code = node.get("code") or node.get("value") or node.get("id")
    children = node.get("subLevelModelList") or node.get("children") or node.get("subList")

    current = path + [name] if name else path
    if children:
        _walk(children, current, out)
    elif name and code is not None:
        out.append({
            "code": str(code),
            "name": name,
            # 保留完整路径，便于按大类聚合与观察抓取进度。
            "path": " > ".join(current),
            "top": current[0] if current else "",
        })


def extract_categories(payload: dict) -> list[dict]:
    data = payload.get("zpData") if isinstance(payload, dict) else None
    if data is None:
        data = payload
    # condition.json 把类目放在 position 字段下
    if isinstance(data, dict):
        data = data.get("position") or data.get("positionList") or data
    out: list[dict] = []
    _walk(data, [], out)

    unique: dict[str, dict] = {}
    for item in out:
        unique.setdefault(item["code"], item)
    return sorted(unique.values(), key=lambda x: (x["top"], x["code"]))


def show_existing() -> int:
    if not OUTPUT_PATH.is_file():
        print(f"码表不存在: {OUTPUT_PATH}")
        return 1
    data = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
    categories = data.get("categories", [])
    print(f"分类总数: {len(categories)}  来源: {data.get('source', '?')}")
    tops: dict[str, int] = {}
    for item in categories:
        tops[item["top"]] = tops.get(item["top"], 0) + 1
    for top, count in sorted(tops.items(), key=lambda kv: -kv[1]):
        print(f"  {top or '(未分组)'}: {count}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--show", action="store_true", help="只查看已有码表")
    args = parser.parse_args()
    if args.show:
        return show_existing()

    last_error = ""
    for url in CATEGORY_URLS:
        try:
            print(f"尝试: {url}")
            payload = _fetch_via_cdp(url)
            categories = extract_categories(payload)
            if not categories:
                last_error = "接口返回中未解析出分类节点"
                print("  未解析出分类，换下一个来源")
                continue
            OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
            OUTPUT_PATH.write_text(
                json.dumps({"source": url, "categories": categories}, ensure_ascii=False, indent=1),
                encoding="utf-8",
            )
            print(f"  已保存 {len(categories)} 个分类 -> {OUTPUT_PATH}")
            return show_existing()
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            print(f"  失败: {exc}")

    print(f"\n全部来源均失败: {last_error}")
    print("请确认已启动登录版 Chrome（9222 端口）后重试。")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
