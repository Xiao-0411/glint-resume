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
if not exist "%SOURCE%\Default" (
  echo Chrome Default profile not found: "%SOURCE%\Default"
  pause
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -Command "$c=Get-NetTCPConnection -LocalPort 9222 -State Listen -ErrorAction SilentlyContinue; if($c){ exit 0 }; exit 1"
if not errorlevel 1 (
  echo Chrome remote debugging is already listening on port 9222.
  echo Starting crawler using the existing browser session.
  start "GlintCrawler" /D "%~dp0backend" cmd.exe /k ".venv\Scripts\python.exe run_crawler.py"
  endlocal
  exit /b 0
)

echo Close every normal Chrome window first.
echo On first run, your Default profile will be copied locally so existing logins are retained.
pause

tasklist /FI "IMAGENAME eq chrome.exe" 2>nul | find /I "chrome.exe" >nul
if not errorlevel 1 (
  echo Chrome is still running. Close every Chrome window and run this file again.
  pause
  exit /b 1
)

if not exist "%MARKER%" (
  echo Copying the Default Chrome profile. This may take a minute...
  if not exist "%PROFILE%" mkdir "%PROFILE%"
  copy /Y "%SOURCE%\Local State" "%PROFILE%\Local State" >nul
  robocopy "%SOURCE%\Default" "%PROFILE%\Default" /E /R:1 /W:1 /NFL /NDL /NJH /NJS /NP /XD "Cache" "Code Cache" "GPUCache" "Service Worker\CacheStorage" >nul
  if errorlevel 8 (
    echo Failed to copy the Chrome profile.
    pause
    exit /b 1
  )
  type nul > "%MARKER%"
)

rem START requires an empty window title before the executable path.
start "" "%CHROME%" --remote-debugging-port=9222 --user-data-dir="%PROFILE%" --profile-directory=Default --no-first-run --no-default-browser-check
if errorlevel 1 (
  echo Failed to start Chrome. Make sure all Chrome windows are closed.
  pause
  exit /b 1
)

echo Chrome started on http://127.0.0.1:9222.
echo Verify that Liepin, Boss Zhipin, and Zhaopin are logged in.
echo Then press any key to start the crawler using this same browser.
pause >nul
start "GlintCrawler" /D "%~dp0backend" cmd.exe /k ".venv\Scripts\python.exe run_crawler.py"
endlocal
