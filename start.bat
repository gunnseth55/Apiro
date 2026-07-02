@echo off
REM Apiro AI Detective — Windows Startup Script
REM =============================================
REM Double-click to launch. Opens http://localhost:8000 automatically.
REM Reads settings from .env if present.

title Apiro AI Detective

echo.
echo  ==========================================
echo   Apiro Clinical AI Detective
echo  ==========================================
echo.

REM Load .env file if it exists
if exist .env (
    echo  [*] Loading .env configuration...
    for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
        if not "%%A"=="" if not "%%A:~0,1%"=="#" (
            set "%%A=%%B"
        )
    )
)

REM Check if Ollama is running
curl -s http://localhost:11434/api/tags >nul 2>&1
if %errorlevel% neq 0 (
    echo  [!] Ollama is not running!
    echo      Please start Ollama first:  ollama serve
    echo      Or use Docker:              docker compose up
    echo.
    pause
    exit /b 1
)
echo  [+] Ollama is running.

REM Show active model
if defined PRIMARY_MODEL (
    echo  [*] Model: %PRIMARY_MODEL%
) else (
    echo  [*] Model: mistral:latest (default)
)

REM Activate the virtual environment
call venv\Scripts\activate.bat

REM Start the server
set PORT=8000
if defined APP_PORT set PORT=%APP_PORT%
echo  [*] Starting Apiro on http://localhost:%PORT%
echo  [*] Press Ctrl+C to stop.
echo.

REM Open browser after a short delay
start /b cmd /c "timeout /t 3 >nul && start http://localhost:%PORT%"

uvicorn scripts.app:app --host 0.0.0.0 --port %PORT%

pause
