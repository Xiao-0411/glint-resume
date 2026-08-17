"""采集环境诊断：不抓数据入库，只检查三个平台能不能拿到接口数据。

用法：
    cd backend
    .venv\\Scripts\\python.exe diagnose_login.py

会自动拉起采集专用 Chrome（和爬虫用的是同一个），逐个平台报告：
登录态、是否被风控、能不能解析出职位、薪资是否为明文。
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.crawlers.api_capture import build_search_url, classify
from app.crawlers.cdp_collector import (
    CAPTURE_TIMEOUT,
    CDP_PORT,
    PLATFORM_LABELS,
    UnifiedCDPCollector,
)

PROBE_JS = """(() => {
  let stackRead = false;
  const e = new Error();
  Object.defineProperty(e, 'stack', {get(){ stackRead = true; return ''; }});
  console.debug(e);
  return JSON.stringify({
    webdriver: navigator.webdriver,
    hidden: document.hidden,
    visibility: document.visibilityState,
    hasFocus: document.hasFocus(),
    runtimeEnableDetected: stackRead,
    url: location.href
  });
})()"""


def header(title):
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


async def main():
    header(f"1. 准备采集专用 Chrome（CDP 端口 {CDP_PORT}）")
    collector = UnifiedCDPCollector()
    try:
        # 只开标签页、不等人工登录，登录态由下面逐平台报告
        await asyncio.to_thread(_open_only, collector)
    except Exception as exc:
        print(f"启动失败: {exc}")
        return 1

    print(f"已打开 {len(collector.tabs)} 个采集标签页")

    header("2. 浏览器指纹自检（应全部为「正常」）")
    tab = next(iter(collector.tabs.values()))
    import json as _json

    raw = await asyncio.to_thread(tab.cdp.eval_js, PROBE_JS, tab.session_id)
    try:
        probe = _json.loads(raw) if isinstance(raw, str) else (raw or {})
    except (ValueError, TypeError):
        probe = {}
    checks = [
        ("navigator.webdriver", probe.get("webdriver"), False, "true 会被直接识别为自动化"),
        ("document.hidden", probe.get("hidden"), False, "true 会触发可见性反爬"),
        ("visibilityState", probe.get("visibility"), "visible", "hidden 会被判定为后台机器人"),
        ("document.hasFocus()", probe.get("hasFocus"), True, "false 说明焦点仿真没生效"),
        ("Runtime.enable 可探测", probe.get("runtimeEnableDetected"), False, "true 说明暴露了 CDP"),
    ]
    for name, got, want, why in checks:
        mark = "正常" if got == want else "异常"
        extra = "" if got == want else f"  <- {why}"
        print(f"  [{mark}] {name:24} = {got!r}{extra}")

    header("3. 逐平台探测")
    any_ok = False
    for platform, tab in collector.tabs.items():
        label = PLATFORM_LABELS[platform]
        print(f"\n--- {label} ---")
        await asyncio.to_thread(tab.drain)
        url = build_search_url(platform, "Java", 1, collector.city)
        await asyncio.to_thread(tab.navigate, url)
        await asyncio.sleep(3)
        got = await asyncio.to_thread(tab.wait_response, CAPTURE_TIMEOUT)
        if got is None:
            await asyncio.to_thread(tab.human_scroll)
            got = await asyncio.to_thread(tab.wait_response, CAPTURE_TIMEOUT)

        cur = await asyncio.to_thread(tab.current_url)
        print(f"  当前 URL : {cur[:82]}")
        if any(m in cur.lower() for m in ("/web/user/", "login", "passport")):
            print("  结论     : 被跳到登录页 —— 需要在专用 Chrome 里登录该平台")
            continue
        if got is None:
            print("  结论     : 未捕获到搜索接口响应")
            print("             接口路径可能变了。用 F12 Network 找真实路径，")
            print("             补到 api_capture.py 的 API_PATH_CANDIDATES 里。")
            continue

        status, data = got
        result = classify(platform, status, data)
        print(f"  HTTP     : {status} -> {result.status.value}")
        print(f"  判定     : {result.describe()}")
        print(f"  解析职位 : {len(result.jobs)} 条")
        if result.jobs:
            j = result.jobs[0]
            print(f"  样例     : {j['title']} | {j['salary']} | {j['company']}")
            if j["salary"]:
                print("  薪资明文 : 是（接口通道正常）")
                any_ok = True
            else:
                print("  薪资明文 : 否 —— 可能未登录或接口未返回 salaryDesc")

    await collector.close()

    header("结论")
    if any_ok:
        print("至少一个平台可正常采集。直接运行 启动爬虫.bat 即可。")
    else:
        print("没有平台成功拿到数据。按顺序排查：")
        print("  1) 在专用 Chrome 里登录对应平台（爬虫会自动等你登录）")
        print("  2) 关掉 VPN/代理 —— 平台对代理出口 IP 有独立风控")
        print("  3) 用 F12 Network 核对接口路径是否变更")
    return 0


def _open_only(collector):
    """只拉起 Chrome 和标签页，跳过等待人工登录那一步。"""
    from app.crawlers.cdp_collector import PlatformTab, _load_vendor

    collector.vendor = _load_vendor()
    collector._ensure_chrome()
    collector.cdp = collector.vendor.CDPSession(CDP_PORT)
    for platform in PLATFORM_LABELS:
        tab = PlatformTab(collector.vendor, collector.cdp, platform)
        tab.open()
        collector.tabs[platform] = tab
    collector.platforms = list(collector.tabs)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
