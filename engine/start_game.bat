@echo off
title ASTRO-HEROES Marswalk
cd /d "%~dp0"
echo ==========================================
echo   ASTRO-HEROES ^| Marswalk Mission
echo ==========================================
where python >nul 2>nul
if errorlevel 1 (
  echo Python is not installed. Install it from https://www.python.org/downloads/ ^(tick "Add to PATH"^) then run this file again.
  pause
  exit /b 1
)
echo Installing Python packages (first time only)...
python -m pip install --quiet --disable-pip-version-check fastapi uvicorn rasterio pyproj scipy matplotlib pandas requests
if not exist "web\curiosity.geojson" (
  echo Building the real Curiosity traverse dataset from NASA...
  python run_curiosity.py
)
echo Starting the route engine...
start "" cmd /c "timeout /t 30 >nul & start http://localhost:8000"
echo The game opens in your browser in about 30 seconds: http://localhost:8000
python -m uvicorn api:app --port 8000
pause
