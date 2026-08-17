@echo off
setlocal EnableExtensions

set "CHROME=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME%" set "CHROME=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME%" set "CHROME=%LocalAppData%\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME%" (
  echo Chrome not found. Set CHROME in this file to your chrome.exe path.
  pause
  exit /b 1
)

set "SOURCE=%LocalAppData%\Google\Chrome\User Data"
set "PROFILE=%~dp0backend\.crawler_chrome_profile_connected"
set "MARKER=%PROFILE%\.profile_seeded"

powershell -NoProfile -ExecutionPolicy Bypass -Command "$c=Get-NetTCPConnection -LocalPort 9222 -State Listen -ErrorAction SilentlyContinue; if($c){ exit 0 }; exit 1"
if not errorlevel 1 (
  echo Chrome remote debugging is already listening on port 9222.
  echo Starting crawler using the existing browser session.
  start "GlintCrawler" /D "%~dp0backend" cmd.exe /k ".venv\Scripts\python.exe run_crawler.py"
  endlocal
  exit /b 0
)

echo Close every normal Chrome window first.
echo.
echo This uses a SEPARATE Chrome profile for crawling.
echo The first time, you must log in to Boss Zhipin / Liepin / Zhaopin
echo inside the browser window that opens. That login is then remembered.
pause

tasklist /FI "IMAGENAME eq chrome.exe" 2>nul | find /I "chrome.exe" >nul
if not errorlevel 1 (
  echo Chrome is still running. Close every Chrome window and run this file again.
  pause
  exit /b 1
)

rem The dedicated profile was seeded once from the main Chrome profile and now
rem holds its own logins. Never re-copy over a working profile: re-copying can
rem clobber a good session, and on Chrome 127+ cookies are sealed with
rem App-Bound Encryption tied to the original install, so a fresh copy may not
rem decrypt at all. If the crawler profile ever loses its login, just log in
rem again inside the window this script opens.
if not exist "%PROFILE%" mkdir "%PROFILE%"
if not exist "%MARKER%" (
  echo First run: a dedicated crawler Chrome profile will be created.
  echo You will need to log in to the job sites inside the window that opens.
  type nul > "%MARKER%"
)

rem START requires an empty window title before the executable path.
rem Keep --remote-debugging-port on a fixed non-zero port: port 0 would make
rem Chrome report navigator.webdriver = true and give the anti-bot a free tell.
start "" "%CHROME%" --remote-debugging-port=9222 --user-data-dir="%PROFILE%" --profile-directory=Default --no-first-run --no-default-browser-check

if errorlevel 1 (
  echo Failed to start Chrome. Make sure all Chrome windows are closed.
  pause
  exit /b 1
)

echo.
echo Chrome started on http://127.0.0.1:9222.
echo Log in to Boss Zhipin, Liepin and Zhaopin in THIS window if you have not.
echo Leave the Boss Zhipin tab in the FOREGROUND if you can.
echo Then press any key to start the crawler using this same browser.
pause >nul
start "GlintCrawler" /D "%~dp0backend" cmd.exe /k ".venv\Scripts\python.exe run_crawler.py"
endlocal
