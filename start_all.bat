@echo off
rem Starts the RailMentes backend (http://127.0.0.1:8000) and frontend (http://localhost:5173) in two windows.
rem Run once beforehand: see README.md "Setup".
setlocal
cd /d "%~dp0"

if not exist "backend\.venv\Scripts\python.exe" (
    echo [ERROR] Backend virtual environment not found. Follow README.md Setup first.
    exit /b 1
)

if not exist "frontend\node_modules" (
    echo [ERROR] Frontend dependencies missing. Run "npm install" in frontend\ first.
    exit /b 1
)

start "RailMentes backend" cmd /k "cd /d backend && .venv\Scripts\python.exe -m uvicorn app.api.main:app --host 127.0.0.1 --port 8000 --reload --reload-dir app"
start "RailMentes frontend" cmd /k "cd /d frontend && npm run dev"

echo Backend API docs: http://127.0.0.1:8000/docs
echo Frontend:         http://localhost:5173
endlocal
