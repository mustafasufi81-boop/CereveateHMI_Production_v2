@echo off
title Cereveate Historian Query Tool
color 0B

echo ================================
echo   HISTORIAN QUERY TOOL
echo ================================
echo.
echo Starting Flask server...
echo.
echo Web Interface: http://localhost:7005
echo.

cd /d "%~dp0"
python historian_query_tool.py

pause
