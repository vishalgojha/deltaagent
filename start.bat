@echo off
setlocal
cd /d "%~dp0"

echo ============================================
echo DeltaAgent One-Click Start
echo ============================================

where docker >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Docker is not installed or not in PATH.
  echo Install Docker Desktop and try again.
  pause
  exit /b 1
)

docker info >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Docker Engine is not running.
  echo Open Docker Desktop and wait until it shows "Engine running", then run start.bat again.
  echo If it still fails, restart Docker Desktop once.
  pause
  exit /b 1
)

echo [1/3] Starting Postgres + Redis via Docker...
docker compose up -d postgres redis
if errorlevel 1 (
  echo [ERROR] Failed to start Docker services.
  pause
  exit /b 1
)

set "PYTHON_EXE="
if exist ".\.venv\Scripts\python.exe" (
  set "PYTHON_EXE=.\.venv\Scripts\python.exe"
)

if not defined PYTHON_EXE (
  for /d %%d in (.\.venv*) do (
    if exist "%%d\Scripts\python.exe" (
      set "PYTHON_EXE=%%d\Scripts\python.exe"
      goto :python_ready
    )
  )
)

:python_ready
if not defined PYTHON_EXE (
  echo [ERROR] Python virtual env not found.
  echo Expected one of:
  echo   .\.venv\Scripts\python.exe
  echo   .\.venv*\Scripts\python.exe
  echo Create it first, then run this script again.
  echo Example:
  echo   py -3.11 -m venv .venv
  pause
  exit /b 1
)

echo [2/3] Starting Backend (new window)...
echo [INFO] Using Python runtime: %PYTHON_EXE%
start "DeltaAgent Backend" cmd /k "cd /d %~dp0 && %PYTHON_EXE% -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload"

if not exist ".\frontend\package.json" (
  echo [ERROR] Frontend package.json not found.
  pause
  exit /b 1
)

echo [3/3] Starting Frontend (new window)...
start "DeltaAgent Frontend" cmd /k "cd /d %~dp0frontend && npm.cmd run dev"

echo.
echo Started.
echo Backend:  http://localhost:8000
echo Frontend: http://localhost:5173
echo.
echo To stop everything, run stop.bat
echo.
endlocal
