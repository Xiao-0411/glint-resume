"""
职位爬虫 - 独立运行入口
启动:  python run_crawler.py
启动可见浏览器完成三个平台登录后，按 backend/.env 中配置的秒数抓取职位数据并存入 MySQL
"""
import asyncio
import sys
import os

# 确保 backend 目录在 Python 路径中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.logging_config import setup_logging
from app.crawlers.scheduler import CRAWL_INTERVAL_SECONDS, run_scheduler

if __name__ == "__main__":
    setup_logging(level="INFO")
    print(f"🚀 职位爬虫调度器启动，三个平台共用 CDP 登录浏览器，每 {CRAWL_INTERVAL_SECONDS} 秒抓取一次...")
    print("   按 Ctrl+C 停止")
    try:
        asyncio.run(run_scheduler())
    except KeyboardInterrupt:
        print("\n⏹ 爬虫调度器已停止")
