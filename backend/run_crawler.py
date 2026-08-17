"""
职位爬虫 - 独立运行入口
启动:  python run_crawler.py

三个平台（BOSS直聘/智联招聘/猎聘）统一走原生 CDP 引擎：自动拉起采集专用
Chrome、自动检测登录态（首次需人工登录一次），之后每 2 小时自动抓取并入库。
"""
import asyncio
import sys
import os

# 确保 backend 目录在 Python 路径中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.logging_config import setup_logging
from app.crawlers.scheduler import run_scheduler

if __name__ == "__main__":
    setup_logging(level="INFO")
    print("职位爬虫启动：自动准备采集专用 Chrome，每 2 小时抓取一次。")
    print("按 Ctrl+C 停止")
    try:
        asyncio.run(run_scheduler())
    except KeyboardInterrupt:
        print("\n爬虫调度器已停止")
