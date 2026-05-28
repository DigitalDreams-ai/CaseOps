@echo off
setlocal enabledelayedexpansion

echo.
echo ============================================
echo CaseOps Multi-Instance Stopper
echo ============================================
echo.

:: Kill all Flask servers on ports 5000 and 5351
echo Stopping CaseOps instances...
for /f "tokens=5" %%p in ('netstat -ano 2^>nul ^| findstr ":5000 " ^| findstr "LISTENING"') do (
    taskkill /PID %%p /F >nul 2>&1
    echo - Killed process on port 5000 (PID: %%p)
)
for /f "tokens=5" %%p in ('netstat -ano 2^>nul ^| findstr ":5351 " ^| findstr "LISTENING"') do (
    taskkill /PID %%p /F >nul 2>&1
    echo - Killed process on port 5351 (PID: %%p)
)

:: Kill comments poller
echo.
echo Stopping Comments Poller...
for /f "tokens=5" %%p in ('netstat -ano 2^>nul ^| findstr "comments_poller" ^| findstr "LISTENING"') do (
    taskkill /PID %%p /F >nul 2>&1
    echo - Killed Comments Poller (PID: %%p)
)

echo.
echo ============================================
echo All instances stopped.
echo ============================================
echo.
pause
