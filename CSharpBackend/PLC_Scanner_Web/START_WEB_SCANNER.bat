@echo off
echo ========================================
echo  PLC SCANNER - WEB INTERFACE
echo ========================================
echo.
echo Starting web server on port 7001...
echo Dashboard will be available at:
echo   http://localhost:7001
echo.
echo Press Ctrl+C to stop
echo ========================================
echo.

cd /d "%~dp0"
python plc_scanner_web.py

pause
