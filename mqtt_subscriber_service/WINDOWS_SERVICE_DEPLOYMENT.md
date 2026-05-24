# MQTT Subscriber Service - Windows Service Deployment Guide

## Overview
Complete guide for deploying the MQTT Subscriber Service as a Windows Service.

---

## Prerequisites

### Required Software
1. **Python 3.10+**
   - Download: https://www.python.org/downloads/
   - Ensure "Add Python to PATH" is checked during installation

2. **PostgreSQL 14+**
   - Database: `Historian_data` must exist
   - Port: 5432 (default)

3. **Mosquitto MQTT Broker**
   - Download: https://mosquitto.org/download/
   - Port: 1883 (default)

4. **Administrator Privileges**
   - Required for service installation

---

## Quick Start (Automated Deployment)

### Option 1: Complete Automated Deployment
```batch
# Run as Administrator
deploy_complete.bat
```

This will:
1. Install Python dependencies
2. Deploy database schema
3. Create database user
4. Install Windows service
5. Verify installation

---

## Manual Deployment Steps

### Step 1: Install Dependencies
```batch
pip install -r requirements.txt
pip install pywin32
```

### Step 2: Deploy Database Schema
```batch
# Create tables
psql -U postgres -d Historian_data -f sql\create_subscriber_tables.sql

# Create user
psql -U postgres -d Historian_data -f sql\create_user.sql

# Verify deployment
psql -U postgres -d Historian_data -f sql\verify_deployment.sql
```

### Step 3: Configure Service
Edit `config\service_config.yaml`:
```yaml
database:
  host: "localhost"
  port: 5432
  database: "Historian_data"
  username: "opc_app_user"
  password: "YOUR_PASSWORD_HERE"

mqtt:
  broker_host: "localhost"
  broker_port: 1883
```

### Step 4: Install Windows Service
```batch
# Run as Administrator
install_service.bat
```

Or manually:
```batch
python windows_service.py install
```

### Step 5: Start Service
```batch
start_service.bat
```

Or:
```batch
net start MQTTSubscriberService
```

---

## Service Management

### Start Service
```batch
# Option 1: Batch file
start_service.bat

# Option 2: NET command
net start MQTTSubscriberService

# Option 3: SC command
sc start MQTTSubscriberService

# Option 4: Services GUI
services.msc  # Find "MQTT Subscriber Service" and start
```

### Stop Service
```batch
# Option 1: Batch file
stop_service.bat

# Option 2: NET command
net stop MQTTSubscriberService

# Option 3: SC command
sc stop MQTTSubscriberService
```

### Check Service Status
```batch
# Option 1: Batch file
check_status.bat

# Option 2: SC query
sc query MQTTSubscriberService

# Option 3: PowerShell
Get-Service MQTTSubscriberService
```

### Restart Service
```batch
net stop MQTTSubscriberService
net start MQTTSubscriberService
```

### Uninstall Service
```batch
# Option 1: Batch file
uninstall_service.bat

# Option 2: Manual
python windows_service.py remove
```

---

## Service Configuration

### Service Details
- **Service Name**: `MQTTSubscriberService`
- **Display Name**: MQTT Subscriber Service
- **Description**: Enterprise MQTT data subscriber service
- **Startup Type**: Manual (change to Automatic for auto-start)

### Set Auto-Start
```batch
sc config MQTTSubscriberService start=auto
```

### Set Manual Start
```batch
sc config MQTTSubscriberService start=demand
```

---

## Testing the Service

### 1. Verify Service is Running
```batch
check_status.bat
```

### 2. Generate Test Data
```batch
cd tests
python mqtt_topic_test_generator.py
```

### 3. Check Database
```sql
-- Check audit records
SELECT * FROM historian_raw.mqtt_audit_main 
ORDER BY first_received_time DESC LIMIT 10;

-- Check processing status
SELECT status, COUNT(*) 
FROM historian_raw.mqtt_audit_main 
GROUP BY status;

-- Check timeseries data
SELECT * FROM historian_raw.historian_timeseries 
ORDER BY time DESC LIMIT 10;
```

### 4. Monitor Logs
```batch
# View all logs
type logs\mqtt_subscriber.log

# View last 20 lines
powershell -command "Get-Content logs\mqtt_subscriber.log -Tail 20"

# View errors only
type logs\mqtt_subscriber_errors.log
```

---

## Troubleshooting

### Service Won't Start

**Check Prerequisites:**
```batch
# Check Python
python --version

# Check PostgreSQL
psql -U postgres -d Historian_data -c "SELECT version();"

# Check MQTT broker
python -c "import paho.mqtt.client as mqtt; c=mqtt.Client(); c.connect('localhost',1883,60); print('OK')"
```

**Check Logs:**
```batch
type logs\mqtt_subscriber.log
type logs\mqtt_subscriber_errors.log
```

**Check Windows Event Viewer:**
1. Open Event Viewer (eventvwr.msc)
2. Navigate to: Windows Logs > Application
3. Look for events from "MQTTSubscriberService"

### Database Connection Errors

**Verify Connection:**
```batch
psql -U opc_app_user -d Historian_data -c "SELECT 1;"
```

**Common Issues:**
- Wrong password in config
- PostgreSQL not running
- Firewall blocking port 5432
- User permissions not granted

**Fix:**
```batch
# Re-run user creation
psql -U postgres -d Historian_data -f sql\create_user.sql
```

### MQTT Connection Errors

**Verify MQTT Broker:**
```batch
# Check if Mosquitto is running
sc query mosquitto

# Test connection
python -c "import paho.mqtt.client as mqtt; c=mqtt.Client(); c.connect('localhost',1883,60); print('Connected')"
```

**Common Issues:**
- Mosquitto not running
- Wrong broker address in config
- Firewall blocking port 1883

**Fix:**
```batch
# Start Mosquitto
net start mosquitto
```

### Permission Errors

**Run as Administrator:**
- Right-click batch file
- Select "Run as administrator"

**Check Service Permissions:**
```batch
sc sdshow MQTTSubscriberService
```

---

## Monitoring

### Real-Time Log Monitoring
```batch
# PowerShell (keeps updating)
powershell -command "Get-Content logs\mqtt_subscriber.log -Wait -Tail 50"
```

### Performance Metrics
```sql
-- Messages processed (last hour)
SELECT 
    COUNT(*) as total_messages,
    COUNT(*) FILTER (WHERE status='completed') as successful,
    COUNT(*) FILTER (WHERE status='failed') as failed,
    AVG(processing_duration_ms) as avg_duration_ms
FROM historian_raw.mqtt_audit_main
WHERE first_received_time > NOW() - INTERVAL '1 hour';
```

### Service Health Check
```batch
# Use the status check script
check_status.bat
```

---

## Maintenance

### Update Configuration
1. Stop the service
2. Edit `config\service_config.yaml`
3. Start the service

```batch
net stop MQTTSubscriberService
notepad config\service_config.yaml
net start MQTTSubscriberService
```

### Update Service Code
1. Stop the service
2. Update Python files
3. Restart the service

```batch
net stop MQTTSubscriberService
# Update files
net start MQTTSubscriberService
```

### Backup Configuration
```batch
# Backup config
copy config\service_config.yaml config\service_config.yaml.backup

# Backup logs
xcopy logs logs_backup\ /E /I /Y
```

### Log Rotation
Logs automatically rotate when they reach 100MB (configured in logging_config.json).

Manual cleanup:
```batch
# Archive old logs
move logs\*.log.1 logs\archive\

# Or delete old logs
del logs\*.log.*
```

---

## Advanced Configuration

### Change Service Account
By default, service runs as Local System. To run as specific user:

```batch
# Stop service
net stop MQTTSubscriberService

# Change account
sc config MQTTSubscriberService obj="DOMAIN\Username" password="password"

# Start service
net start MQTTSubscriberService
```

### Service Recovery Options
Configure automatic restart on failure:

```batch
# Restart service on failure
sc failure MQTTSubscriberService reset=86400 actions=restart/5000/restart/10000/restart/20000
```

### Firewall Rules
If running on a server, allow required ports:

```batch
# Allow PostgreSQL
netsh advfirewall firewall add rule name="PostgreSQL" dir=in action=allow protocol=TCP localport=5432

# Allow MQTT
netsh advfirewall firewall add rule name="MQTT" dir=in action=allow protocol=TCP localport=1883
```

---

## Uninstallation

### Complete Removal
```batch
# 1. Stop and uninstall service
uninstall_service.bat

# 2. (Optional) Remove database objects
psql -U postgres -d Historian_data -c "DROP TABLE IF EXISTS historian_raw.mqtt_audit_history CASCADE;"
psql -U postgres -d Historian_data -c "DROP TABLE IF EXISTS historian_raw.mqtt_audit_main CASCADE;"
psql -U postgres -d Historian_data -c "DROP TABLE IF EXISTS historian_raw.mqtt_topic_config CASCADE;"

# 3. (Optional) Remove database user
psql -U postgres -d Historian_data -c "DROP USER IF EXISTS opc_app_user;"

# 4. Delete service folder
cd ..
rmdir /S mqtt_subscriber_service
```

---

## Support

### Log Files Location
```
logs\
  mqtt_subscriber.log           - Main service log
  mqtt_subscriber_errors.log    - Errors only
  mqtt_subscriber_security.log  - Security events
```

### Configuration Files
```
config\
  service_config.yaml   - Main configuration
  logging_config.json   - Logging configuration
```

### Database Tables
```sql
historian_raw.mqtt_topic_config    - Topic configuration
historian_raw.mqtt_audit_main      - Message audit trail
historian_raw.mqtt_audit_history   - Processing history
historian_raw.historian_timeseries - Time-series data
historian_raw.historian_events     - Alarm/event data
```

---

## Best Practices

1. **Always run as Administrator** when installing/uninstalling
2. **Backup configuration** before making changes
3. **Monitor logs regularly** for errors
4. **Test after deployment** using test data generator
5. **Set up automatic restart** for production
6. **Enable log rotation** to manage disk space
7. **Monitor database growth** and archive old data
8. **Keep credentials secure** (encrypt passwords in production)

---

## Production Checklist

- [ ] PostgreSQL installed and running
- [ ] Mosquitto MQTT broker installed and running
- [ ] Database schema deployed
- [ ] Database user created with correct permissions
- [ ] Service configuration reviewed and updated
- [ ] Windows service installed
- [ ] Service starts successfully
- [ ] Test data processed successfully
- [ ] Logs directory created and writable
- [ ] Service set to auto-start (if desired)
- [ ] Service recovery options configured
- [ ] Monitoring/alerting configured
- [ ] Backup procedures established
- [ ] Documentation reviewed with team

---

**Last Updated**: January 8, 2026
