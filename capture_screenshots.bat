@echo off
setlocal
cd /d "%~dp0"

echo ============================================
echo DeltaAgent Docs Screenshot Capture
echo ============================================

if not exist ".\frontend\package.json" (
  echo [ERROR] frontend\package.json not found.
  pause
  exit /b 1
)

echo [1/1] Running Playwright screenshot flow...
cd /d "%~dp0frontend"
npm.cmd run screenshots:e2e
if errorlevel 1 (
  echo [ERROR] Screenshot capture failed.
  echo Check backend/frontend startup logs and try again.
  pause
  exit /b 1
)

echo.
echo Screenshots generated in:
echo   %~dp0docs\screenshots
echo.
echo Next:
echo   git add docs/screenshots/*.png
echo   git commit -m "Add product screenshots"
echo   git push origin main
echo.
endlocal
