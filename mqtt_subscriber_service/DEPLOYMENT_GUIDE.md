# MQTT Subscriber Service - Deployment Guide

## Overview

This guide provides step-by-step instructions for deploying the MQTT Subscriber Service in production environments.

## Pre-Deployment Checklist

- [ ] Python 3.10+ installed on target server
- [ ] PostgreSQL 14+ with TimescaleDB extension running
- [ ] MQTT broker accessible from target server
- [ ] Network connectivity verified (database, MQTT)
- [ ] Service account created with appropriate permissions
- [ ] Firewall rules configured
- [ ] SSL/TLS certificates obtained (if using secure MQTT)

## Deployment Steps

### 1. Server Preparation

#### Install Python 3.10+

```batch
# Download Python 3.10+ from python.org
# Verify installation
python --version
```

#### Install Git (if not present)

```batch
# Download Git from git-scm.com
git --version
```

### 2. Deploy Application Files

#### Option A: Copy Files

```batch
# Create deployment directory
mkdir C:\Services\MQTTSubscriber
cd C:\Services\MQTTSubscriber

# Copy application files
xcopy /E /I /Y \\source\mqtt_subscriber_service\* .
```

#### Option B: Clone Repository

```batch
# Clone from repository
git clone https://your-repo/mqtt_subscriber_service.git
cd mqtt_subscriber_service
```

### 3. Database Setup

#### Create Database User

```sql
-- Create service user
CREATE USER mqtt_subscriber_user WITH PASSWORD 'secure_password_here';

-- Grant permissions
GRANT USAGE ON SCHEMA historian_raw TO mqtt_subscriber_user;
GRANT USAGE ON SCHEMA historian_meta TO mqtt_subscriber_user;

-- Grant table permissions
GRANT ALL ON TABLE historian_raw.mqtt_topic_config TO mqtt_subscriber_user;
GRANT ALL ON TABLE historian_raw.mqtt_audit_main TO mqtt_subscriber_user;
GRANT ALL ON TABLE historian_raw.mqtt_audit_history TO mqtt_subscriber_user;
GRANT INSERT ON TABLE historian_raw.historian_timeseries TO mqtt_subscriber_user;
GRANT INSERT ON TABLE historian_raw.historian_events TO mqtt_subscriber_user;

-- Grant SELECT on tag_master (READ-ONLY)
GRANT SELECT ON TABLE historian_meta.tag_master TO mqtt_subscriber_user;
```

#### Create Service Tables

```batch
# Run schema creation script
psql -h localhost -U postgres -d historian_db -f sql\create_subscriber_tables.sql
```

#### Verify Schema

```sql
-- Verify tables exist
SELECT table_name 
FROM information_schema.tables 
WHERE table_schema = 'historian_raw' 
  AND table_name LIKE 'mqtt_%';

-- Should return:
-- mqtt_topic_config
-- mqtt_audit_main
-- mqtt_audit_history
```

### 4. Configure Service

#### Edit Configuration File

```batch
notepad config\service_config.yaml
```

**Production Configuration:**

```yaml
service:
  name: mqtt_subscriber_service
  version: 1.0.0
  environment: production

database:
  host: prod-db-server.domain.com
  port: 5432
  database: historian_db
  user: mqtt_subscriber_user
  password: ${DB_PASSWORD}  # Use environment variable
  pool_min_connections: 5
  pool_max_connections: 20
  connect_timeout: 10

mqtt:
  broker: mqtt-broker.domain.com
  port: 8883  # TLS port
  username: mqtt_subscriber
  password: ${MQTT_PASSWORD}  # Use environment variable
  client_id: mqtt_subscriber_prod_01
  keepalive: 60
  clean_session: false

processing:
  worker_threads: 16  # Increase for production
  task_queue_size: 5000
  max_payload_size_bytes: 1048576
  validate_against_tag_master: true
  topic_cache_refresh_interval: 300

security:
  enable_tls: true
  tls:
    ca_cert: C:\certs\ca.crt
    client_cert: C:\certs\client.crt
    client_key: C:\certs\client.key
  enable_credential_encryption: true
  encryption_key_path: C:\secure\encryption.key
  enable_input_sanitization: true

logging:
  level: INFO
  max_file_size_mb: 100
  backup_count: 10

monitoring:
  enable_health_endpoint: true
  health_check_interval: 30
  metrics_log_interval: 300  # 5 minutes
```

#### Set Environment Variables

```batch
# Create environment variable script
notepad set_environment.bat
```

**set_environment.bat:**

```batch
@echo off
REM Production environment variables

set DB_HOST=prod-db-server.domain.com
set DB_PORT=5432
set DB_NAME=historian_db
set DB_USER=mqtt_subscriber_user
set DB_PASSWORD=your_secure_db_password

set MQTT_BROKER=mqtt-broker.domain.com
set MQTT_PORT=8883
set MQTT_USERNAME=mqtt_subscriber
set MQTT_PASSWORD=your_secure_mqtt_password

echo Environment variables set for production
```

### 5. Install Python Dependencies

```batch
# Navigate to service directory
cd C:\Services\MQTTSubscriber

# Run installation script
install.bat
```

Or manually:

```batch
# Create virtual environment
python -m venv venv

# Activate virtual environment
venv\Scripts\activate.bat

# Install dependencies
pip install -r requirements.txt

deactivate
```

### 6. Configure MQTT Topics

Insert topic configurations into database:

```sql
INSERT INTO historian_raw.mqtt_topic_config 
(topic_name, qos, enabled, data_schema, description)
VALUES 
('plant/sensors/temperature', 1, true, 
 '{"type": "object", "properties": {"tag_id": {"type": "string"}, "value": {"type": "number"}}}'::jsonb,
 'Temperature sensor data'),
 
('plant/sensors/pressure', 1, true,
 '{"type": "object", "properties": {"tag_id": {"type": "string"}, "value": {"type": "number"}}}'::jsonb,
 'Pressure sensor data'),
 
('plant/alarms/#', 2, true,
 '{"type": "object", "properties": {"tag_id": {"type": "string"}, "value": {"type": "string"}}}'::jsonb,
 'Alarm events');
```

### 7. Test Service

#### Run Health Check

```batch
# Activate virtual environment
venv\Scripts\activate.bat

# Run health check
python scripts\health_check.py

deactivate
```

Expected output:

```
========================================
MQTT Subscriber Service - Health Check
========================================

✓ Configuration: VALID
✓ Database: HEALTHY

========================================
Overall Status: HEALTHY ✓
```

#### Test Service Manually

```batch
# Set environment variables
call set_environment.bat

# Run service in console
run_service.bat
```

Watch for startup messages:

```
============================================================
MQTT Subscriber Service Starting...
============================================================
Initializing service components...
1/8 Initializing database connection...
✓ Database connected
2/8 Initializing Data Access Objects...
✓ DAOs initialized
...
All components initialized successfully
MQTT Subscriber Service is running...
```

Press `Ctrl+C` to stop.

### 8. Install as Windows Service

#### Using NSSM (Recommended)

```batch
# Download NSSM from nssm.cc
# Extract to C:\Tools\nssm

# Install service
C:\Tools\nssm\win64\nssm.exe install MQTTSubscriberService

# Configure service in NSSM GUI:
# - Path: C:\Services\MQTTSubscriber\venv\Scripts\python.exe
# - Startup directory: C:\Services\MQTTSubscriber
# - Arguments: src\service_main.py

# Or use command line:
C:\Tools\nssm\win64\nssm.exe set MQTTSubscriberService AppDirectory "C:\Services\MQTTSubscriber"
C:\Tools\nssm\win64\nssm.exe set MQTTSubscriberService AppEnvironmentExtra DB_PASSWORD=your_password MQTT_PASSWORD=your_password

# Start service
C:\Tools\nssm\win64\nssm.exe start MQTTSubscriberService
```

#### Verify Service Status

```batch
# Check service status
sc query MQTTSubscriberService

# View service logs
type C:\Services\MQTTSubscriber\logs\mqtt_subscriber_service.log
```

### 9. Configure Service Auto-Start

```batch
# Set service to start automatically
sc config MQTTSubscriberService start= auto

# Set recovery options (restart on failure)
sc failure MQTTSubscriberService reset= 86400 actions= restart/60000/restart/60000/restart/60000
```

### 10. Monitoring Setup

#### Configure Log Rotation

Logs are automatically rotated (see config):
- Max file size: 100 MB
- Backup count: 10 files
- Location: `C:\Services\MQTTSubscriber\logs\`

#### Setup Windows Event Viewer (Optional)

Create a PowerShell script to forward critical errors:

**monitor_logs.ps1:**

```powershell
# Monitor log file and create Windows events for errors
$logFile = "C:\Services\MQTTSubscriber\logs\mqtt_subscriber_service_error.log"

Get-Content $logFile -Wait | ForEach-Object {
    if ($_ -match "CRITICAL|ERROR") {
        Write-EventLog -LogName Application -Source "MQTTSubscriber" -EventId 1001 -EntryType Error -Message $_
    }
}
```

#### Setup Performance Monitoring

Create scheduled task to collect metrics:

```batch
# Create metrics collection script
notepad collect_metrics.bat
```

**collect_metrics.bat:**

```batch
@echo off
REM Collect service metrics

cd C:\Services\MQTTSubscriber
call venv\Scripts\activate.bat

python -c "from src.service_main import MQTTSubscriberService; s = MQTTSubscriberService(); s.initialize(); print(s.get_metrics())" > metrics_%date:~-4,4%%date:~-10,2%%date:~-7,2%.json

deactivate
```

## Post-Deployment Verification

### 1. Service Health Check

```batch
# Check service is running
sc query MQTTSubscriberService

# Run health check
python scripts\health_check.py
```

### 2. Database Connectivity

```sql
-- Check recent audit records
SELECT 
    message_id,
    topic,
    status,
    received_at
FROM historian_raw.mqtt_audit_main
ORDER BY received_at DESC
LIMIT 10;
```

### 3. MQTT Connectivity

Check service logs for connection status:

```batch
findstr /C:"Connected to MQTT broker" logs\mqtt_subscriber_service.log
```

### 4. Message Processing

Send test MQTT message and verify:

```sql
-- Check timeseries data
SELECT 
    time,
    tag_id,
    value_num,
    quality
FROM historian_raw.historian_timeseries
ORDER BY time DESC
LIMIT 10;

-- Check audit trail
SELECT 
    am.message_id,
    am.topic,
    am.status,
    ah.step,
    ah.status as step_status
FROM historian_raw.mqtt_audit_main am
LEFT JOIN historian_raw.mqtt_audit_history ah ON am.audit_id = ah.audit_id
ORDER BY am.received_at DESC
LIMIT 20;
```

## Troubleshooting

### Service Won't Start

1. Check Windows Event Viewer
2. Review error log: `logs\mqtt_subscriber_service_error.log`
3. Verify database connectivity: `scripts\health_check.py`
4. Check file permissions on service directory

### Database Connection Errors

```
ERROR: Database connection test failed
```

**Solutions:**
1. Verify database server is accessible
2. Check firewall rules
3. Verify credentials
4. Test connection manually:

```batch
psql -h prod-db-server.domain.com -U mqtt_subscriber_user -d historian_db
```

### MQTT Connection Errors

```
ERROR: Failed to connect to MQTT broker
```

**Solutions:**
1. Verify MQTT broker is running
2. Check network connectivity
3. Verify TLS certificates (if using TLS)
4. Test with MQTT client tool (e.g., MQTT Explorer)

### High Memory Usage

**Optimization:**
1. Reduce `worker_threads` in config
2. Reduce `task_queue_size`
3. Reduce `pool_max_connections`
4. Enable log rotation

### Processing Delays

**Optimization:**
1. Increase `worker_threads`
2. Increase database connection pool
3. Add database indexes:

```sql
CREATE INDEX idx_timeseries_time ON historian_raw.historian_timeseries(time DESC);
CREATE INDEX idx_timeseries_tag_time ON historian_raw.historian_timeseries(tag_id, time DESC);
```

## Backup and Recovery

### Database Backup

```batch
REM Backup database
pg_dump -h prod-db-server.domain.com -U postgres -d historian_db -F c -f mqtt_subscriber_backup_%date:~-4,4%%date:~-10,2%%date:~-7,2%.dump

REM Backup service configuration
xcopy /E /I /Y C:\Services\MQTTSubscriber\config C:\Backups\MQTTSubscriber\config_%date:~-4,4%%date:~-10,2%%date:~-7,2%
```

### Recovery

```batch
REM Restore database
pg_restore -h prod-db-server.domain.com -U postgres -d historian_db mqtt_subscriber_backup.dump

REM Restore configuration
xcopy /E /I /Y C:\Backups\MQTTSubscriber\config C:\Services\MQTTSubscriber\config

REM Restart service
net stop MQTTSubscriberService
net start MQTTSubscriberService
```

## Maintenance

### Update Service

```batch
# Stop service
net stop MQTTSubscriberService

# Backup current version
xcopy /E /I /Y C:\Services\MQTTSubscriber C:\Backups\MQTTSubscriber\backup_%date:~-4,4%%date:~-10,2%%date:~-7,2%

# Copy new version files
xcopy /E /I /Y \\source\mqtt_subscriber_service\src C:\Services\MQTTSubscriber\src

# Update dependencies (if needed)
cd C:\Services\MQTTSubscriber
venv\Scripts\activate.bat
pip install -r requirements.txt --upgrade
deactivate

# Start service
net start MQTTSubscriberService

# Verify
python scripts\health_check.py
```

### Log Management

```batch
REM Archive old logs
cd C:\Services\MQTTSubscriber\logs
mkdir archive
move mqtt_subscriber_service.log.* archive\

REM Compress archived logs
powershell Compress-Archive -Path archive\* -DestinationPath archive_%date:~-4,4%%date:~-10,2%%date:~-7,2%.zip
del /Q archive\*.log.*
```

## Security Hardening

### File Permissions

```batch
REM Restrict access to service directory
icacls C:\Services\MQTTSubscriber /inheritance:r
icacls C:\Services\MQTTSubscriber /grant:r Administrators:F
icacls C:\Services\MQTTSubscriber /grant:r SYSTEM:F
icacls C:\Services\MQTTSubscriber /grant:r "NT SERVICE\MQTTSubscriberService":(OI)(CI)RX

REM Restrict config directory
icacls C:\Services\MQTTSubscriber\config /grant:r Administrators:F
icacls C:\Services\MQTTSubscriber\config /grant:r "NT SERVICE\MQTTSubscriberService":R
```

### Credential Management

- Store passwords in environment variables (not in config files)
- Use Windows Credential Manager for sensitive data
- Enable credential encryption in config
- Rotate passwords regularly

### Network Security

- Use TLS for MQTT connections
- Use SSL for database connections
- Restrict network access with firewall rules
- Use VPN for remote database access

## Appendix

### Service Account Setup

```batch
REM Create service account
net user MQTTSubscriberSvc /add /passwordreq:yes /passwordchg:no
net localgroup "Users" MQTTSubscriberSvc /add

REM Grant log on as service right
ntrights +r SeServiceLogonRight -u MQTTSubscriberSvc
```

### Firewall Rules

```batch
REM Allow PostgreSQL connection
netsh advfirewall firewall add rule name="PostgreSQL" dir=out action=allow protocol=TCP remoteport=5432

REM Allow MQTT connection
netsh advfirewall firewall add rule name="MQTT" dir=out action=allow protocol=TCP remoteport=8883
```

---

**Document Version:** 1.0  
**Last Updated:** 2024-01-15
