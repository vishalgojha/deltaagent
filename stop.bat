@echo off
setlocal
cd /d "%~dp0"

echo ============================================
echo DeltaAgent One-Click Stop
echo ============================================

echo [1/2] Closing backend/frontend terminal windows...
taskkill /FI "WINDOWTITLE eq DeltaAgent Backend*" /T /F >nul 2>nul
taskkill /FI "WINDOWTITLE eq DeltaAgent Frontend*" /T /F >nul 2>nul

echo [2/2] Stopping Docker services...
docker compose down

echo.
echo Stopped.
echo.
endlocal
