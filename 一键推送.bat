@echo off
rem ============================================================
rem  Glint resume - one-click push
rem
rem  Flow: secret scan -> backend tests -> frontend build
rem        -> show changes -> confirm -> commit -> push
rem  Any failing step aborts before anything is pushed.
rem
rem  NOTE: this file is intentionally ASCII-only. cmd.exe reads
rem  .bat files in the system codepage (GBK on this machine), and
rem  UTF-8 Chinese text gets split mid-sequence and corrupts
rem  parsing. All Chinese output comes from the Python helper.
rem ============================================================
cd /d "%~dp0"
setlocal enabledelayedexpansion

set "REPO_DIR=%~dp0"
set "BACKEND_DIR=%~dp0backend"
set "FRONTEND_DIR=%~dp0frontend"
set "VENV_PYTHON=%BACKEND_DIR%\.venv\Scripts\python.exe"

rem Node detection mirrors the startup launcher: PATH may still point
rem at the old drive letter after the rename.
set "NPM_CMD="
for /f "delims=" %%I in ('where npm.cmd 2^>nul') do if not defined NPM_CMD set "NPM_CMD=%%I"
if not defined NPM_CMD if exist "I:\node.js\npm.cmd" set "NPM_CMD=I:\node.js\npm.cmd"

echo ============================================================
echo   Glint - one-click push
echo ============================================================
echo.

rem ---------- 0. environment ----------
where git >nul 2>&1
if errorlevel 1 (
    echo [X] git not found. Please install Git first.
    goto :fail
)

git rev-parse --is-inside-work-tree >nul 2>&1
if errorlevel 1 (
    echo [X] Not a git repository: %REPO_DIR%
    goto :fail
)

for /f "delims=" %%B in ('git rev-parse --abbrev-ref HEAD') do set "BRANCH=%%B"
echo Current branch: !BRANCH!
echo.

rem ---------- 1. anything to push? ----------
set "DIRTY=0"
git diff --quiet || set "DIRTY=1"
git diff --cached --quiet || set "DIRTY=1"
for /f %%C in ('git ls-files --others --exclude-standard ^| find /c /v ""') do if not "%%C"=="0" set "DIRTY=1"

if "!DIRTY!"=="0" (
    echo [i] Working tree is clean.
    git rev-parse --abbrev-ref @{u} >nul 2>&1
    if errorlevel 1 (
        echo [i] No upstream set for this branch. Nothing to do.
        goto :end
    )
    for /f %%N in ('git rev-list --count @{u}..HEAD') do set "AHEAD=%%N"
    if "!AHEAD!"=="0" (
        echo [i] No unpushed commits. Nothing to do.
        goto :end
    )
    echo.
    echo Unpushed commits:
    git log --oneline @{u}..HEAD
    echo.
    set /p "PUSHONLY=Push these commits now? (y/N) "
    if /i not "!PUSHONLY!"=="y" goto :cancelled
    goto :do_push
)

rem ---------- 2. secret scan ----------
echo [1/4] Scanning for secrets...
if not exist "%VENV_PYTHON%" (
    echo     [!] venv python not found, SKIPPING secret scan.
    echo         Expected: %VENV_PYTHON%
) else (
    "%VENV_PYTHON%" -X utf8 "%REPO_DIR%scripts\check_secrets.py"
    if errorlevel 1 (
        echo.
        echo [X] Secret scan failed. Push aborted.
        goto :fail
    )
    echo     [OK] no obvious secrets
)
echo.

rem ---------- 3. backend tests ----------
echo [2/4] Running backend tests...
if not exist "%VENV_PYTHON%" (
    echo     [!] venv python not found, SKIPPING backend tests.
) else (
    pushd "%BACKEND_DIR%"
    "%VENV_PYTHON%" -X utf8 -m unittest discover -s tests
    if errorlevel 1 (
        popd
        echo.
        echo [X] Backend tests failed. Push aborted.
        goto :fail
    )
    popd
    echo     [OK] backend tests passed
)
echo.

rem ---------- 4. frontend build ----------
echo [3/4] Building frontend...
if not defined NPM_CMD (
    echo     [!] npm not found, SKIPPING frontend build.
) else (
    if not exist "%FRONTEND_DIR%\node_modules" (
        echo     [!] frontend\node_modules missing, SKIPPING build.
        echo         Run "npm install" in frontend to enable this check.
    ) else (
        pushd "%FRONTEND_DIR%"
        call "!NPM_CMD!" run build
        if errorlevel 1 (
            popd
            echo.
            echo [X] Frontend build failed. Push aborted.
            echo     Cloudflare Pages would fail too. Fix it first.
            goto :fail
        )
        popd
        echo     [OK] frontend build passed
    )
)
echo.

rem ---------- 5. show changes ----------
echo [4/4] Changes to be committed:
echo ------------------------------------------------------------
git add -A
git status --short
echo ------------------------------------------------------------
git diff --cached --stat
echo ------------------------------------------------------------
echo.

rem Re-run the checker on the staged set. It also enforces the
rem forbidden-path rules (.env / logs/ / .env.bak), which live in
rem Python rather than findstr so they can be unit-tested.
if exist "%VENV_PYTHON%" (
    "%VENV_PYTHON%" -X utf8 "%REPO_DIR%scripts\check_secrets.py"
    if errorlevel 1 (
        echo.
        echo [X] Staged files failed the safety check. Unstaging.
        git reset >nul
        goto :fail
    )
)

rem ---------- 6. confirm ----------
set "MSG="
set /p "MSG=Commit message (empty = cancel): "
if "!MSG!"=="" goto :cancelled_reset

if /i "!BRANCH!"=="main" (
    echo.
    echo [!] You are pushing directly to main.
    echo     Cloudflare Pages will rebuild the site.
    set "SURE="
    set /p "SURE=Type yes to continue: "
    if /i not "!SURE!"=="yes" goto :cancelled_reset
)

echo.
git commit -m "!MSG!"
if errorlevel 1 (
    echo [X] Commit failed.
    goto :fail
)

:do_push
echo.
echo Pushing to origin/!BRANCH! ...
git push origin "!BRANCH!"
if errorlevel 1 (
    echo.
    echo [X] Push failed. Common causes:
    echo     - remote has new commits: run  git pull --rebase
    echo     - expired credentials or network issue
    goto :fail
)

echo.
echo ============================================================
echo   [OK] pushed: !BRANCH!
echo ============================================================
if /i "!BRANCH!"=="main" (
    echo.
    echo Cloudflare Pages build: https://dash.cloudflare.com
)
goto :end

:cancelled_reset
git reset >nul
:cancelled
echo.
echo Cancelled. Nothing was committed.
goto :end

:fail
echo.
pause
exit /b 1

:end
echo.
pause
exit /b 0
