@echo off
setlocal EnableExtensions

rem 启动 BOSS 专用浏览器（独立 profile，不碰你日常 Chrome 的登录态）。
rem BOSS 用的是 vendor/boss_zhipin_scraper 的原生 CDP 脚本：它只发
rem Page.navigate / Network.enable，不发 Runtime.enable，比 Playwright 隐蔽得多。
rem 首次运行需要你在弹出的窗口里登录一次 zhipin.com，之后会一直记住。

set "PY=%~dp0backend\.venv\Scripts\python.exe"
set "SCRIPT=%~dp0backend\vendor\boss_zhipin_scraper\scripts\boss_cdp_raw.py"
set "PORT=9333"

if not exist "%PY%" (
  echo Python venv not found: "%PY%"
  pause
  exit /b 1
)
if not exist "%SCRIPT%" (
  echo Vendor script not found: "%SCRIPT%"
  pause
  exit /b 1
)

set PYTHONIOENCODING=utf-8

echo ============================================================
echo   BOSS Zhipin dedicated browser
echo ============================================================
echo.
echo Checking environment...
"%PY%" "%SCRIPT%" --check --cdp-port %PORT%
if not errorlevel 1 (
  echo.
  echo Already logged in and ready. Nothing to do.
  echo You can now run the crawler.
  pause
  exit /b 0
)

echo.
echo Launching the dedicated Chrome for BOSS...
echo If a login page appears, log in to zhipin.com in THAT window.
echo The script waits until login is confirmed.
echo.
"%PY%" "%SCRIPT%" --setup-chrome --cdp-port %PORT%
if errorlevel 1 (
  echo.
  echo Setup failed. Common causes:
  echo   - login not completed in time  ^(rerun this file^)
  echo   - port %PORT% already in use   ^(edit PORT in this file^)
  echo   - VPN/proxy on                 ^(turn it off, BOSS flags proxy exit IPs^)
  pause
  exit /b 1
)

echo.
echo ============================================================
echo   BOSS browser ready. Leave this Chrome window open.
echo ============================================================
echo Now run 启动登录浏览器.bat for Liepin/Zhaopin and the crawler.
pause
endlocal
