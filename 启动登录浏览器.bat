@echo off
setlocal EnableExtensions

set "ROOT=%~dp0"
set "BACKEND=%ROOT%backend"
set "PYTHON=%BACKEND%\.venv\Scripts\python.exe"
set "SCRAPER=%BACKEND%\vendor\boss-zhipin-scraper\scripts\boss_cdp_raw.py"
set "LOGIN_MONITOR=%BACKEND%\scripts\monitor_recruitment_logins.py"

if not exist "%PYTHON%" (
  echo Python virtual environment not found: "%PYTHON%"
  echo Run the one-click launcher once or create backend\.venv first.
  pause
  exit /b 1
)
if not exist "%SCRAPER%" (
  echo Vendored BOSS scraper not found: "%SCRAPER%"
  pause
  exit /b 1
)
if not exist "%LOGIN_MONITOR%" (
  echo Three-site login monitor not found: "%LOGIN_MONITOR%"
  pause
  exit /b 1
)

echo Starting the dedicated recruitment Chrome profile on CDP port 9222...
echo BOSS Zhipin, Zhaopin and Liepin will share this isolated login session.
"%PYTHON%" "%SCRAPER%" --setup-chrome --cdp-port 9222 --no-wait-login
if errorlevel 1 (
  echo Failed to start or verify the recruitment CDP browser.
  pause
  exit /b 1
)

"%PYTHON%" "%LOGIN_MONITOR%" --cdp-port 9222 --timeout 900 --interval 3
if errorlevel 1 (
  echo One or more recruitment sites are not ready.
  pause
  exit /b 1
)

echo All three recruitment sites are ready.
echo Next, run the one-click launcher to start the application and crawler.
endlocal
