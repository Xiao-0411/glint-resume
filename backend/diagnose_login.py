"""掉登录问题诊断：不抓数据，只检查连上 CDP 之后 BOSS 会话还在不在。

用法（先跑 启动登录浏览器.bat 起好 Chrome，登录 BOSS，然后）：

    cd backend
    .venv\\Scripts\\python.exe diagnose_login.py

脚本会分三步定位「一启动就掉登录」到底发生在哪个环节：
  1) 只连 CDP，不导航    —— 看连接本身会不会踢掉会话
  2) 装可见性伪装后导航  —— 看当前修复是否生效
  3) 读接口响应判定风控  —— 区分「掉登录」和「被风控」
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from playwright.async_api import async_playwright

from app.crawlers.api_capture import ResponseCapture, build_search_url, classify
from app.crawlers.browser_session import BACKGROUND_VISIBILITY_SCRIPT

CDP_URL = os.getenv("CRAWLER_CDP_URL", "http://127.0.0.1:9222")
PROBE_JS = """(() => {
  let stackRead = false;
  const e = new Error();
  Object.defineProperty(e, 'stack', {get(){ stackRead = true; return ''; }});
  console.debug(e);
  return {
    webdriver: navigator.webdriver,
    hidden: document.hidden,
    visibility: document.visibilityState,
    hasFocus: document.hasFocus(),
    runtimeEnableDetected: stackRead,
    url: location.href,
  };
})()"""


def line(title):
    print("\n" + "=" * 58)
    print(title)
    print("=" * 58)


async def main():
    pw = await async_playwright().start()
    line("1. 连接 CDP（不导航，只看会话是否存活）")
    try:
        browser = await pw.chromium.connect_over_cdp(CDP_URL, no_defaults=True)
    except Exception as exc:
        print(f"连不上 {CDP_URL}: {exc}")
        print("请先运行 启动登录浏览器.bat")
        await pw.stop()
        return 1

    ctx = browser.contexts[0]
    print(f"已连接，现有标签页 {len(ctx.pages)} 个")

    cookies = await ctx.cookies("https://www.zhipin.com")
    names = {c["name"] for c in cookies}
    print(f"zhipin cookie 数: {len(cookies)}")
    for key in ("zp_at", "__zp_stoken__", "wt2", "bst"):
        print(f"  {key:16} {'有' if key in names else '缺失'}")
    if "zp_at" not in names:
        print("  -> 连接前就没有登录 token，问题在浏览器登录态本身，不是爬虫")

    line("2. 打开搜索页（已注入可见性伪装）")
    page = next((p for p in ctx.pages if "zhipin.com" in p.url), None) or await ctx.new_page()
    await page.add_init_script(BACKGROUND_VISIBILITY_SCRIPT)
    try:
        session = await ctx.new_cdp_session(page)
        await session.send("Emulation.setFocusEmulationEnabled", {"enabled": True})
        await session.detach()
        print("焦点仿真已开启")
    except Exception as exc:
        print(f"焦点仿真失败（有 JS 兜底，可忽略）: {exc}")

    capture = ResponseCapture(page, "zhipin")
    capture.attach()
    capture.drain()

    url = build_search_url("zhipin", "Java开发", 1)
    await page.goto(url, wait_until="domcontentloaded", timeout=45000)
    await asyncio.sleep(3)

    probe = await page.evaluate(PROBE_JS)
    print(f"最终 URL          : {probe['url'][:88]}")
    print(f"navigator.webdriver: {probe['webdriver']}   (true 就是明显特征)")
    print(f"document.hidden    : {probe['hidden']}   (必须是 False)")
    print(f"visibilityState    : {probe['visibility']}  (必须是 visible)")
    print(f"document.hasFocus(): {probe['hasFocus']}")
    print(f"Runtime.enable 可被探测: {probe['runtimeEnableDetected']}")

    bounced = any(m in probe["url"].lower() for m in ("/web/user/", "login"))
    print(f"\n是否被踢回登录页  : {'是 —— 掉登录复现了' if bounced else '否 —— 会话存活'}")

    line("3. 读接口响应，区分掉登录 / 风控 / 正常")
    got = await capture.wait_next(timeout=25)
    if got is None:
        print("没捕获到 joblist 接口响应。")
        print("可能：页面结构变了、接口路径变了，或请求根本没发出（被拦在前面）。")
    else:
        status, data = got
        result = classify("zhipin", status, data)
        print(f"HTTP {status} -> {result.status.value}")
        print(f"判定: {result.describe()}")
        print(f"解析到职位: {len(result.jobs)} 条")
        if result.jobs:
            j = result.jobs[0]
            print(f"样例: {j['title']} | {j['salary']} | {j['company']}")
            print("薪资是明文说明接口通道正常。")

    capture.detach()
    await pw.stop()

    line("结论")
    if bounced:
        print("确认掉登录。可见性伪装没能挡住，需要进一步排查：")
        print("  - 换成只连单个标签页的原生 CDP（避开 Playwright 对所有标签页的 Runtime.enable）")
        print("  - 检查是否挂了 VPN/代理：参考项目里有人就是关掉 Clash 后恢复正常的")
    else:
        print("会话存活，掉登录问题已缓解。可以正常启动爬虫。")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
