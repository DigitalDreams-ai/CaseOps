@echo off
setlocal enabledelayedexpansion
set ROOT_DIR=C:\Users\sean\Projects\Salesforce\DigitalDreams\CaseOps
set PYTHON=C:\Users\sean\AppData\Local\Programs\Python\Python312\python.exe

:: Stop any existing Flask server on port 5000
for /f "tokens=5" %%p in ('netstat -ano 2^>nul ^| findstr ":5000 " ^| findstr "LISTENING"') do (
    taskkill /PID %%p /F >nul 2>&1
)

:: Change to root directory
cd /d "%ROOT_DIR%"

:: Start the comments poller (background) with explicit working directory
start "Comments Poller" /B /D "%ROOT_DIR%" "%PYTHON%" "%ROOT_DIR%\scripts\comments_poller.py"

:: Start the GUI server (foreground)
"%PYTHON%" app.py
