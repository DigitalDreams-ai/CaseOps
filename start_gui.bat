@echo off
:: Stop any existing Flask server on port 5000
for /f "tokens=5" %%p in ('netstat -ano 2^>nul ^| findstr ":5000 " ^| findstr "LISTENING"') do (
    taskkill /PID %%p /F >nul 2>&1
)
:: Start the GUI server
cd /d "C:\Users\sean\Projects\Salesforce\DigitalDreams\CaseOps"
"C:\Users\sean\AppData\Local\Programs\Python\Python312\python.exe" app.py
