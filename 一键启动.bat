@echo off
cd /d "%~dp0"
setlocal enabledelayedexpansion

set "BACKEND_DIR=%~dp0backend"
set "FRONTEND_DIR=%~dp0frontend"
set "VENV_PYTHON=%BACKEND_DIR%\.venv\Scripts\python.exe"
set "LOG_DIR=%~dp0logs"
set "FRONTEND_LOG=%LOG_DIR%\frontend.log"
set "NODE_EXE="
set "NPM_CMD="

for /f "delims=" %%I in ('where node.exe 2^>nul') do if not defined NODE_EXE set "NODE_EXE=%%I"
for /f "delims=" %%I in ('where npm.cmd 2^>nul') do if not defined NPM_CMD set "NPM_CMD=%%I"

rem Explorer may still have the old E: PATH after the drive was renamed to I:.
if not defined NODE_EXE if exist "I:\node.js\node.exe" set "NODE_EXE=I:\node.js\node.exe"
if not defined NPM_CMD if exist "I:\node.js\npm.cmd" set "NPM_CMD=I:\node.js\npm.cmd"

if not defined NODE_EXE (
    echo ERROR: Node.js was not found.
    echo Expected location: I:\node.js\node.exe
    echo Please reinstall Node.js or update the Node.js path in this launcher.
    pause
    exit /b 1
)
if not defined NPM_CMD (
    echo ERROR: npm was not found.
    echo Expected location: I:\node.js\npm.cmd
    echo Please reinstall Node.js or update the npm path in this launcher.
    pause
    exit /b 1
)

for %%I in ("%NODE_EXE%") do set "NODE_DIR=%%~dpI"
set "PATH=%NODE_DIR%;%PATH%"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

echo ============================================
echo   Glint - One Click Launcher
echo ============================================
echo.
echo Starting: Backend + Frontend + Crawler
echo Close this window to stop all services
echo.

echo [1/3] Checking MySQL...
cd /d "%BACKEND_DIR%"
"%VENV_PYTHON%" -c "from app.core.database import engine; engine.connect(); print('ok')" 2>nul
if !errorlevel! neq 0 (
    echo.
    echo ============================================
    echo   ERROR: Cannot connect to MySQL
    echo.
    echo   Please make sure:
    echo   1. phpstudy MySQL is running
    echo   2. DATABASE_URL in backend\.env is correct
    echo ============================================
    echo.
    pause
    exit /b 1
)
echo [OK] MySQL connected
echo.

echo [Check] Backend dependencies...
if not exist "%VENV_PYTHON%" (
    echo Creating virtual environment...
    python -m venv "%BACKEND_DIR%\.venv"
    if !errorlevel! neq 0 (
        echo ERROR: Failed to create virtual environment
        pause
        exit /b 1
    )
)
"%VENV_PYTHON%" -c "import fastapi" 2>nul
if !errorlevel! neq 0 (
    echo Installing backend dependencies...
    "%VENV_PYTHON%" -m pip install -r "%BACKEND_DIR%\requirements.txt" -q
    if !errorlevel! neq 0 (
        echo ERROR: Failed to install backend dependencies
        pause
        exit /b 1
    )
)
echo [OK] Backend dependencies ready

echo [Check] Frontend dependencies...
for /f "delims=" %%I in ('"%NODE_EXE%" --version') do echo [OK] Node.js %%I ^(%NODE_EXE%^)
if not exist "%FRONTEND_DIR%\node_modules\" (
    echo Installing frontend dependencies...
    cd /d "%FRONTEND_DIR%"
    call "%NPM_CMD%" install
    if !errorlevel! neq 0 (
        echo ERROR: Failed to install frontend dependencies
        cd /d "%~dp0"
        pause
        exit /b 1
    )
    cd /d "%~dp0"
)
echo [OK] Frontend dependencies ready
echo.

echo [2/3] Starting Backend (port 8000)...
start "GlintBackend" /MIN cmd /c "cd /d "%BACKEND_DIR%" && "%VENV_PYTHON%" -m uvicorn main:app --reload --host 127.0.0.1 --port 8000"
echo [OK] Backend started

echo Waiting for backend to start...
timeout /t 4 /nobreak >nul

echo [3/3] Starting Frontend (port 5173)...
start "GlintFrontend" /MIN /D "%FRONTEND_DIR%" cmd /d /c call "%NPM_CMD%" run dev -- --host 127.0.0.1 --strictPort ^> "%FRONTEND_LOG%" 2^>^&1
echo Waiting for frontend to start...
powershell -NoProfile -Command "$deadline=(Get-Date).AddSeconds(20); do { $client=$null; try { $client=New-Object Net.Sockets.TcpClient; $client.Connect('127.0.0.1',5173); $client.Dispose(); exit 0 } catch { if ($client) { $client.Dispose() } }; Start-Sleep -Milliseconds 500 } while ((Get-Date) -lt $deadline); exit 1" >nul 2>&1
if !errorlevel! neq 0 (
    echo.
    echo ============================================
    echo   ERROR: Frontend failed to start on port 5173
    echo   Log: %FRONTEND_LOG%
    echo ============================================
    echo.
    if exist "%FRONTEND_LOG%" type "%FRONTEND_LOG%"
    pause
    exit /b 1
)
echo [OK] Frontend started

echo [Extra] Starting Job Crawler (every 2 hours)...
start "GlintCrawler" /MIN cmd /c "cd /d "%BACKEND_DIR%" && "%VENV_PYTHON%" run_crawler.py"
echo [OK] Crawler started
echo.

echo ============================================
echo   ALL SERVICES STARTED SUCCESSFULLY!
echo.
echo   Frontend: http://localhost:5173/
echo   Backend:  http://localhost:8000/docs
echo   Crawler:  running in background (every 2h)
echo.
echo   Close this window to stop all services
echo ============================================
echo.

pause >nul

echo.
echo Stopping all services...
taskkill /FI "WINDOWTITLE eq GlintBackend*" /T /F 2>nul
taskkill /FI "WINDOWTITLE eq GlintFrontend*" /T /F 2>nul
taskkill /FI "WINDOWTITLE eq GlintCrawler*" /T /F 2>nul
echo All services stopped
pause >nul
