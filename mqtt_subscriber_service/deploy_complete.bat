@echo off
REM ============================================================================
REM MQTT Subscriber Service - Complete Deployment Script
REM Automates full deployment: DB setup, service installation, and verification
REM Run as Administrator
REM ============================================================================

echo ============================================================================
echo MQTT Subscriber Service - COMPLETE DEPLOYMENT
echo ============================================================================
echo.
echo This script will:
echo   1. Install Python dependencies
echo   2. Deploy database schema
echo   3. Create database user
echo   4. Install Windows service
echo   5. Verify installation
echo.
echo Prerequisites:
echo   - Python 3.10+ installed
echo   - PostgreSQL 14+ running
echo   - Mosquitto MQTT broker installed
echo   - Administrator privileges
echo.
pause

REM Check for Administrator privileges
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo ERROR: This script must be run as Administrator!
    pause
    exit /b 1
)

echo.
echo ============================================================================
echo STEP 1: Installing Python Dependencies
echo ============================================================================
echo.
pip install -r requirements.txt
if %errorLevel% neq 0 (
    echo ERROR: Failed to install dependencies
    pause
    exit /b 1
)
echo.
echo Dependencies installed successfully!
pause

echo.
echo ============================================================================
echo STEP 2: Deploying Database Schema
echo ============================================================================
echo.
echo Enter PostgreSQL superuser password when prompted...
echo.
psql -U postgres -d Historian_data -f sql\create_subscriber_tables.sql
if %errorLevel% neq 0 (
    echo.
    echo ERROR: Database schema deployment failed
    echo Make sure:
    echo   1. PostgreSQL is running
    echo   2. Historian_data database exists
    echo   3. Credentials are correct
    echo.
    pause
    exit /b 1
)
echo.
echo Database schema deployed successfully!
pause

echo.
echo ============================================================================
echo STEP 3: Creating Database User
echo ============================================================================
echo.
psql -U postgres -d Historian_data -f sql\create_user.sql
if %errorLevel% neq 0 (
    echo.
    echo WARNING: User creation may have failed or user already exists
    echo Continuing...
)
echo.
echo Database user setup complete!
pause

echo.
echo ============================================================================
echo STEP 4: Installing Windows Service
echo ============================================================================
echo.
call install_service.bat
if %errorLevel% neq 0 (
    echo ERROR: Service installation failed
    pause
    exit /b 1
)

echo.
echo ============================================================================
echo STEP 5: Verifying Installation
echo ============================================================================
echo.

echo Checking database tables...
psql -U postgres -d Historian_data -c "SELECT table_name FROM information_schema.tables WHERE table_schema='historian_raw' AND table_name LIKE 'mqtt_%'" -t
echo.

echo Checking service installation...
sc query MQTTSubscriberService
echo.

echo Creating logs directory...
if not exist "logs" mkdir logs
echo Logs directory ready
echo.

echo.
echo ============================================================================
echo DEPLOYMENT COMPLETE!
echo ============================================================================
echo.
echo Next Steps:
echo -----------
echo 1. Review configuration: config\service_config.yaml
echo 2. Start the service: start_service.bat
echo 3. Check status: check_status.bat
echo 4. Generate test data: cd tests ^&^& python mqtt_topic_test_generator.py
echo 5. View logs: type logs\mqtt_subscriber.log
echo.
echo Service Commands:
echo ----------------
echo   Start:   net start MQTTSubscriberService
echo   Stop:    net stop MQTTSubscriberService
echo   Status:  sc query MQTTSubscriberService
echo   Remove:  uninstall_service.bat
echo.
echo Database Verification:
echo ---------------------
echo   psql -U postgres -d Historian_data -c "SELECT * FROM historian_raw.mqtt_topic_config;"
echo   psql -U postgres -d Historian_data -c "SELECT * FROM historian_raw.mqtt_audit_main ORDER BY first_received_time DESC LIMIT 10;"
echo.
echo ============================================================================
pause
