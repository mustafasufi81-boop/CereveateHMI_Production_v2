@echo off
cd /d "%~dp0"

echo Starting C# OPC Service...
start "C# OPC" cmd /c "dotnet run --urls http://localhost:5001"

echo Starting HMI Flask...
cd HMI
start "HMI Flask" cmd /c ".\venv\Scripts\activate && python app.py"

echo.
echo Waiting 10 seconds for services to start...
timeout /t 10 /nobreak

echo.
echo Running test...
python test_hmi_flow.py

pause
