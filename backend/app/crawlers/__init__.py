"""
职位爬虫包

当前只有猎聘（LiepinCrawler）在实际工作。
zhipin / zhaopin 两个爬虫因平台反爬已停用，crawl() 返回空列表，
文件保留了实测结论和接口线索，详见各自模块顶部说明。
"""
from app.crawlers.base import BaseCrawler, JOB_KEYWORDS
from app.crawlers.zhipin import ZhipinCrawler
from app.crawlers.zhaopin import ZhaopinCrawler
from app.crawlers.liepin import LiepinCrawler, LIEPIN_CITIES

__all__ = [
    "BaseCrawler",
    "JOB_KEYWORDS",
    "ZhipinCrawler",
    "ZhaopinCrawler",
    "LiepinCrawler",
    "LIEPIN_CITIES",
]
