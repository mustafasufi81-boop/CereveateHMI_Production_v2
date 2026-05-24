@echo off
REM Install MQTT Subscriber Service Dependencies

echo ========================================
echo Installing MQTT Subscriber Service
echo ========================================
echo.

REM Check Python installation
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python 3.10+ is required
    echo Please install Python from https://www.python.org/downloads/
    pause
    exit /b 1
)

REM Create virtual environment
if not exist "venv\" (
    echo Creating virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment
        pause
        exit /b 1
    )
    echo Virtual environment created.
) else (
    echo Virtual environment already exists.
)

REM Activate virtual environment
echo Activating virtual environment...
call venv\Scripts\activate.bat

REM Upgrade pip
echo Upgrading pip...
python -m pip install --upgrade pip

REM Install dependencies
echo Installing dependencies...
pip install -r requirements.txt

if errorlevel 1 (
    echo ERROR: Failed to install dependencies
    deactivate
    pause
    exit /b 1
)

echo.
echo ========================================
echo Installation Complete!
echo ========================================
echo.
echo Next steps:
echo 1. Configure database connection in config/service_config.yaml
echo 2. Configure MQTT broker connection in config/service_config.yaml
echo 3. Run the SQL script: sql/create_subscriber_tables.sql
echo 4. Start the service: run_service.bat
echo.

deactivate
pause
