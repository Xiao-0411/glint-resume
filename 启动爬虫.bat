@echo off
setlocal EnableExtensions

rem 一键启动爬虫。三个平台（BOSS直聘 / 智联招聘 / 猎聘）统一走
rem vendor/boss_zhipin_scraper 的原生 CDP 引擎：
rem   - 自动拉起采集专用 Chrome（独立 profile，不碰你日常浏览器）
rem   - 自动检测每个平台的登录态，只在需要时让你登录一次
rem   - 之后每 2 小时全自动抓取，无需再做任何操作
rem
rem 你日常用的 Chrome 不需要关闭，两者互不影响。

set "PY=%~dp0backend\.venv\Scripts\python.exe"
if not exist "%PY%" (
  echo Python venv not found: "%PY%"
  echo Run: cd backend ^&^& python -m venv .venv ^&^& .venv\Scripts\pip install -r requirements.txt
  pause
  exit /b 1
)

set PYTHONIOENCODING=utf-8

echo ============================================================
echo   Glint job crawler
echo ============================================================
echo.
echo Platforms: Boss Zhipin / Zhaopin / Liepin
echo A dedicated Chrome will start automatically.
echo On first run, log in to the sites inside THAT window - once only.
echo.
echo Tip: if a platform keeps getting blocked, turn off any VPN/proxy.
echo.

cd /d "%~dp0backend"
"%PY%" run_crawler.py

echo.
echo Crawler stopped.
pause
endlocal
