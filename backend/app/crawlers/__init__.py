"""职位爬虫包。

三个平台（BOSS直聘/智联招聘/猎聘）统一走 cdp_collector 的原生 CDP 引擎，
底层复用 vendor/boss_zhipin_scraper。子模块按需直接导入，这里不做再导出，
避免包初始化时牵连不必要的依赖。
"""
