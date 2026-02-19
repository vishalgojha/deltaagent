@echo off
setlocal
cd /d "%~dp0"

echo ============================================
echo DeltaAgent Status Check
echo ============================================

set BACKEND=DOWN
set FRONTEND=DOWN
set POSTGRES=DOWN
set REDIS=DOWN

where curl >nul 2>nul
if not errorlevel 1 (
  curl -s -o nul -w "%%{http_code}" http://localhost:8000/health > "%temp%\deltaagent_backend_code.txt"
  set /p BACKCODE=<"%temp%\deltaagent_backend_code.txt"
  del "%temp%\deltaagent_backend_code.txt" >nul 2>nul
  if "%BACKCODE%"=="200" set BACKEND=UP

  curl -s -o nul -w "%%{http_code}" http://localhost:5173 > "%temp%\deltaagent_frontend_code.txt"
  set /p FRONTCODE=<"%temp%\deltaagent_frontend_code.txt"
  del "%temp%\deltaagent_frontend_code.txt" >nul 2>nul
  if "%FRONTCODE%"=="200" set FRONTEND=UP
)

for /f "tokens=*" %%i in ('docker compose ps -q postgres 2^>nul') do set POSTGRES_ID=%%i
if defined POSTGRES_ID set POSTGRES=UP

for /f "tokens=*" %%i in ('docker compose ps -q redis 2^>nul') do set REDIS_ID=%%i
if defined REDIS_ID set REDIS=UP

echo Backend  : %BACKEND%  ^(http://localhost:8000/health^)
echo Frontend : %FRONTEND% ^(http://localhost:5173^)
echo Postgres : %POSTGRES%
echo Redis    : %REDIS%

echo.
echo Tip:
echo - Start all: start.bat
echo - Stop all : stop.bat
echo.

endlocal
