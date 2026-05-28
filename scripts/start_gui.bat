@echo off
setlocal enabledelayedexpansion
set ROOT_DIR=C:\Users\sean\Projects\Salesforce\DigitalDreams\CaseOps
set PYTHON=C:\Users\sean\AppData\Local\Programs\Python\Python312\python.exe

echo.
echo ============================================
echo CaseOps Multi-Instance Launcher
echo ============================================
echo.

:: Stop any existing Flask servers on port 5000 and 5351
echo Stopping any existing CaseOps instances...
for /f "tokens=5" %%p in ('netstat -ano 2^>nul ^| findstr ":5000 " ^| findstr "LISTENING"') do (
    taskkill /PID %%p /F >nul 2>&1
    echo - Killed process on port 5000 (PID: %%p)
)
for /f "tokens=5" %%p in ('netstat -ano 2^>nul ^| findstr ":5351 " ^| findstr "LISTENING"') do (
    taskkill /PID %%p /F >nul 2>&1
    echo - Killed process on port 5351 (PID: %%p)
)

:: Change to root directory
cd /d "%ROOT_DIR%"

:: Start the comments poller (background) once for all instances
echo.
echo Starting Comments Poller...
start "Comments Poller" /B /D "%ROOT_DIR%" "%PYTHON%" "%ROOT_DIR%\scripts\comments_poller.py"
echo - Comments Poller started (background)

:: Start Instance 1 (port 5000) in new window
echo.
echo Starting Instance 1 (port 5000)...
start "CaseOps Instance 1" /D "%ROOT_DIR%" "powershell" -NoExit -Command "cd '%ROOT_DIR%'; .\instance1\launch.ps1"
echo - Instance 1 window opened

:: Start Instance 2 (port 5351) in new window
echo.
echo Starting Instance 2 (port 5351)...
start "CaseOps Instance 2" /D "%ROOT_DIR%" "powershell" -NoExit -Command "cd '%ROOT_DIR%'; .\instance2\launch.ps1"
echo - Instance 2 window opened

echo.
echo ============================================
echo All instances started!
echo ============================================
echo.
echo Instance 1: http://localhost:5000
echo Instance 2: http://localhost:5351
echo.
echo Close this window anytime. Instances will continue running.
echo.
pause
