@echo off
echo ============================================================
echo Starting Tag Trend Viewer UI
echo ============================================================
echo.

cd /d "%~dp0"
.\venv\Scripts\python.exe tag_trend_viewer.py

pause
