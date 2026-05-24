@echo off
echo ============================================
echo Historical Trends Viewer - Python Service
echo ============================================
echo.

REM Check if virtual environment exists
if not exist "venv\Scripts\python.exe" (
    echo Creating virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment
        echo Please install Python 3.8 or higher
        pause
        exit /b 1
    )
)

echo Activating virtual environment...
call venv\Scripts\activate.bat

echo Installing/updating required packages...
python -m pip install --upgrade pip
python -m pip install "numpy<2" --force-reinstall --no-deps
python -m pip install -r requirements.txt

echo.
echo Starting Historical Trends service...
echo Service will run on http://localhost:6004
echo.

python app.py

pause
