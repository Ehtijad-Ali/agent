@echo off
REM ============================================================
REM  Signal - stop whatever run-dev.bat started.
REM
REM  Kills the process listening on each port rather than every
REM  node.exe / python.exe on the machine, so unrelated work is
REM  left alone.
REM ============================================================

REM Delayed expansion is deliberately OFF: with it enabled, "!" inside an echo
REM is swallowed as a variable marker, so warnings printed as "[]".
setlocal

echo.
echo  Signal - stopping development services
echo  ============================================================

call :killport 8000 "Backend"
call :killport 3000 "Frontend"

echo.
echo  Done.
echo.
endlocal
exit /b 0

:killport
set "PORT=%~1"
set "LABEL=%~2"
set "FOUND="

REM netstat lists a separate LISTENING row per address family, so one service
REM shows up twice. Without the _seen_ guard the second taskkill runs against
REM an already-dead PID and reports a failure that did not happen.
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /r /c:"LISTENING" ^| findstr /c:":%PORT% "') do (
    if not "%%p"=="0" if not defined _seen_%%p (
        set "_seen_%%p=1"
        set "FOUND=1"
        taskkill /PID %%p /F >nul 2>&1
        if errorlevel 1 (
            echo  [warn] %LABEL% ^(port %PORT%, PID %%p^) would not stop.
            echo         It may belong to another user - try an elevated prompt.
        ) else (
            echo  [ok] Stopped %LABEL% ^(port %PORT%, PID %%p^)
        )
    )
)

if not defined FOUND echo  [--] %LABEL% ^(port %PORT%^) was not running
exit /b 0
