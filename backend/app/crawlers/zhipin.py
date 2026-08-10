"""
Boss直聘 爬虫 —— 已停用

2026-08 实测结论：
- 直接请求 wapi/zpgeek/search/joblist.json 返回 code=37「访问行为异常」，无数据
- Playwright + Edge headless：反爬脚本识别出自动化，页面被跳到 about:blank
- Playwright 有头 + 持久化 profile + 反检测：跳到 verify.html 验证页，code=35

要真正打通需要过滑块验证 + 维护登录态 cookie，属于持续对抗，成本远高于收益。
当前职位数据全部来自猎聘（见 liepin.py）。

保留此文件是为了记录结论，避免以后重复踩坑。如果哪天要重启：
入口是 zhipin.com/web/geek/job 页面，列表数据来自上面那个 joblist.json XHR，
字段结构是 zpData.jobList[]，元素含 encryptJobId/jobName/brandName/salaryDesc/cityName。
"""
import logging
from typing import List

from app.crawlers.base import BaseCrawler

logger = logging.getLogger("glint.crawler.zhipin")

ENABLED = False


class ZhipinCrawler(BaseCrawler):
    platform = "zhipin"
    base_url = "https://www.zhipin.com"

    async def crawl(self, keywords: List[str] = None) -> List[dict]:
        logger.info("zhipin_disabled", extra={"reason": "anti-bot: code=37 / verify page"})
        return []
