@echo off
REM ML Background Learning System - Quick Start
echo ========================================
echo ML BACKGROUND LEARNING SYSTEM
echo ========================================
echo.

cd /d "%~dp0"

echo Starting system...
echo Press Ctrl+C to stop
echo.

..\venv\Scripts\python.exe background_process_manager.py

pause
