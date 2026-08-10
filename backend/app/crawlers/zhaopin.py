"""
智联招聘 爬虫 —— 已停用

2026-08 实测结论：
fe-api.zhaopin.com/c/i/sou 返回 HTTP 200、code=200，看起来一切正常，
但 data.results 恒为空数组（numTotal=0），响应里带 isVerification 字段 ——
说明需要通过验证/登录态才会下发真实数据。老代码判断的是 code==200，
所以它会安静地拿到 0 条职位而不报错，这也是之前"爬虫在跑但库里没数据"的原因之一。

当前职位数据全部来自猎聘（见 liepin.py）。

保留此文件是为了记录结论。如果哪天要重启：
接口是 GET fe-api.zhaopin.com/c/i/sou，参数 kw/p/pageSize/workCity，
返回结构 data.results[]，元素含 number/jobName/company.name/salary/city.display。
"""
import logging
from typing import List

from app.crawlers.base import BaseCrawler

logger = logging.getLogger("glint.crawler.zhaopin")

ENABLED = False


class ZhaopinCrawler(BaseCrawler):
    platform = "zhaopin"
    base_url = "https://www.zhaopin.com"

    async def crawl(self, keywords: List[str] = None) -> List[dict]:
        logger.info("zhaopin_disabled", extra={"reason": "api returns empty results without auth"})
        return []
