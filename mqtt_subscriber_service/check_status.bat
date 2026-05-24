@echo off
REM ============================================================================
REM MQTT Subscriber Service - Service Status Check
REM ============================================================================

echo ============================================================================
echo MQTT Subscriber Service - Status Check
echo ============================================================================
echo.

echo Service Status:
echo ---------------
sc query MQTTSubscriberService
echo.

echo Configuration:
echo --------------
if exist "config\service_config.yaml" (
    echo Config file: OK
) else (
    echo Config file: MISSING
)
echo.

echo Database Connection:
echo -------------------
python -c "import psycopg2; conn = psycopg2.connect(host='localhost', port=5432, database='Historian_data', user='opc_app_user', password='MqttSub$ecure2026!'); print('Database: OK'); conn.close()" 2>nul
if %errorLevel% neq 0 (
    echo Database: NOT CONNECTED
)
echo.

echo MQTT Broker:
echo -----------
python -c "import paho.mqtt.client as mqtt; c = mqtt.Client(); c.connect('localhost', 1883, 60); print('MQTT Broker: OK'); c.disconnect()" 2>nul
if %errorLevel% neq 0 (
    echo MQTT Broker: NOT CONNECTED
)
echo.

echo Recent Logs (last 10 lines):
echo ---------------------------
if exist "logs\mqtt_subscriber.log" (
    powershell -command "Get-Content logs\mqtt_subscriber.log -Tail 10"
) else (
    echo No logs found
)
echo.

echo ============================================================================
pause
