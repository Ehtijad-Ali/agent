@echo off
REM ============================================================
REM  Signal - start the backend and frontend for local development.
REM
REM  Opens two windows:
REM    Signal Backend   http://127.0.0.1:8000   (FastAPI, auto-reload)
REM    Signal Frontend  http://localhost:3000   (Next.js dev server)
REM
REM  Close either window to stop that service, or run stop-dev.bat
REM  to stop both.
REM ============================================================

REM Delayed expansion is deliberately OFF: with it enabled, "!" inside an
REM echo is swallowed as a variable marker, so warnings printed as "[]".
setlocal
cd /d "%~dp0"

set "BACKEND_PORT=8000"
set "FRONTEND_PORT=3000"

echo.
echo  Signal - development startup
echo  ============================================================

REM ---------- prerequisites ----------
where node >nul 2>&1
if errorlevel 1 (
    echo  [X] Node.js not found on PATH.
    echo      Install from https://nodejs.org and reopen this window.
    goto :fail
)

REM Prefer the py launcher; fall back to python.
set "PY=py"
where py >nul 2>&1
if errorlevel 1 (
    set "PY=python"
    where python >nul 2>&1
    if errorlevel 1 (
        echo  [X] Python not found on PATH.
        echo      Install 3.12+ from https://python.org and reopen this window.
        goto :fail
    )
)

REM `node --version` prints a single token ("v24.14.0"), so tokens=2 yields
REM nothing and the echo below degrades to a literal "~0,20".
for /f "tokens=1" %%v in ('node --version 2^>^&1') do set "NODEV=%%v"
echo  [ok] Node %NODEV%
for /f "tokens=*" %%v in ('%PY% --version 2^>^&1') do echo  [ok] %%v

REM ---------- ports already in use? ----------
call :checkport %BACKEND_PORT% "Backend"
call :checkport %FRONTEND_PORT% "Frontend"

REM ---------- backend virtualenv ----------
REM Kept inside backend\.venv so it is gitignored and never mixes with
REM whatever Python packages happen to be installed system-wide.
if not exist "backend\.venv\Scripts\python.exe" (
    echo.
    echo  [..] Creating backend virtualenv ^(first run only^)...
    %PY% -m venv "backend\.venv"
    if errorlevel 1 (
        echo  [X] Could not create the virtualenv.
        goto :fail
    )
)
set "VENV_PY=%~dp0backend\.venv\Scripts\python.exe"

REM Install deps only when FastAPI is missing, so restarts stay fast.
"%VENV_PY%" -c "import fastapi" >nul 2>&1
if errorlevel 1 (
    echo  [..] Installing backend dependencies ^(first run only, ~1-2 min^)...
    "%VENV_PY%" -m pip install --quiet --upgrade pip
    "%VENV_PY%" -m pip install --quiet -r "backend\requirements.txt"
    if errorlevel 1 (
        echo  [X] pip install failed. Run it manually to see the error:
        echo      backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
        goto :fail
    )
)
echo  [ok] Backend dependencies ready

REM ---------- frontend deps ----------
if not exist "node_modules\next" (
    echo  [..] Installing frontend dependencies ^(first run only, a few minutes^)...
    call npm install
    if errorlevel 1 (
        echo  [X] npm install failed.
        goto :fail
    )
)
echo  [ok] Frontend dependencies ready

REM ---------- backend .env ----------
if not exist "backend\.env" (
    if exist "backend\.env.example" (
        copy /y "backend\.env.example" "backend\.env" >nul
        echo  [ok] Created backend\.env from the template
        echo       Engine endpoints run without further setup. Postgres,
        echo       Redis, Ollama and the platform tokens are still blank.
    )
)

REM ---------- launch ----------
echo.
echo  Starting services...
start "Signal Backend" cmd /k "cd /d "%~dp0backend" && "%VENV_PY%" -m uvicorn app.main:app --host 127.0.0.1 --port %BACKEND_PORT% --reload"
start "Signal Frontend" cmd /k "cd /d "%~dp0" && npm run dev"

echo.
echo  ============================================================
echo   Frontend   http://localhost:%FRONTEND_PORT%
echo   Backend    http://127.0.0.1:%BACKEND_PORT%/api
echo   API docs   http://127.0.0.1:%BACKEND_PORT%/docs
echo  ============================================================
echo.
echo  Two windows have opened. The frontend takes a few seconds to
echo  compile on first load.
echo.
echo  Stop everything with:  stop-dev.bat
echo.
endlocal
exit /b 0

REM ---------- helpers ----------
:checkport
REM %1 = port, %2 = label. Warn rather than fail: the port may be held by an
REM earlier run of this script, which the user may well want to keep.
netstat -ano | findstr /r /c:"LISTENING" | findstr /c:":%~1 " >nul 2>&1
if not errorlevel 1 (
    echo  [warn] Port %~1 is already in use ^(%~2^).
    echo         That service may already be running, or stop it with stop-dev.bat
)
exit /b 0

:fail
echo.
echo  Startup aborted.
echo.
endlocal
pause
exit /b 1
