# MQTT Subscriber Service - Quick Reference Guide

## 🚀 Quick Start

### Installation (5 minutes)
```batch
# 1. Run installer
install.bat

# 2. Edit config/service_config.yaml
# - Set database host, user, password
# - Set MQTT broker, user, password

# 3. Run SQL schema
psql -h localhost -U postgres -d historian_db -f sql\create_subscriber_tables.sql

# 4. Start service
run_service.bat
```

### Health Check
```batch
python scripts\health_check.py
```

---

## 📋 Common Commands

### Service Management
```batch
# Start service (console mode)
run_service.bat

# Stop service
Ctrl+C

# Check health
python scripts\health_check.py
```

### Database Operations
```sql
-- Check recent messages
SELECT * FROM historian_raw.mqtt_audit_main 
ORDER BY received_at DESC LIMIT 10;

-- Check processing status
SELECT status, COUNT(*) 
FROM historian_raw.mqtt_audit_main 
GROUP BY status;

-- View timeseries data
SELECT * FROM historian_raw.historian_timeseries 
ORDER BY time DESC LIMIT 10;
```

### Configuration Check
```batch
# View current config
type config\service_config.yaml

# Test database connection
psql -h localhost -U mqtt_subscriber_user -d historian_db
```

---

## 🔧 Configuration Quick Reference

### Database Section
```yaml
database:
  host: localhost              # DB server hostname
  port: 5432                  # PostgreSQL port
  database: historian_db       # Database name
  user: mqtt_subscriber_user   # DB username
  password: ${DB_PASSWORD}     # Use env variable
  pool_max_connections: 20    # Max connections
```

### MQTT Section
```yaml
mqtt:
  broker: mqtt.example.com     # MQTT broker hostname
  port: 1883                  # MQTT port (1883 or 8883)
  username: mqtt_user          # MQTT username
  password: ${MQTT_PASSWORD}   # Use env variable
  client_id: mqtt_sub_01       # Unique client ID
```

### Processing Section
```yaml
processing:
  worker_threads: 8            # Number of workers (4-16)
  task_queue_size: 1000        # Queue size
  validate_against_tag_master: true  # Enable tag validation
  topic_cache_refresh_interval: 300  # Cache refresh (seconds)
```

### Security Section
```yaml
security:
  enable_tls: false            # Enable TLS/mTLS
  enable_input_sanitization: true  # SQL injection prevention
```

---

## 📊 Message Format

### Valid Message (JSON)
```json
{
  "tag_id": "TAG001",          // Required: Tag from tag_master
  "timestamp": "2024-01-15T10:30:00Z",  // Required: ISO 8601
  "value": 123.45,             // Required: numeric, text, or bool
  "quality": "G",              // Optional: G, B, or U
  "source": "MQTT",            // Optional: data source
  "version": 1                 // Optional: mapping version
}
```

### Quality Codes
- **G** - Good (default)
- **B** - Bad
- **U** - Uncertain

---

## 🔍 Troubleshooting

### Service Won't Start
```batch
# Check logs
type logs\mqtt_subscriber_service_error.log

# Test database
python scripts\health_check.py

# Test config
python -c "from src.utils.config_loader import ConfigLoader; ConfigLoader.load('config/service_config.yaml')"
```

### Database Connection Failed
```
❌ Error: Database connection test failed
```
**Fix:**
1. Verify PostgreSQL running: `sc query postgresql`
2. Test connection: `psql -h localhost -U mqtt_subscriber_user -d historian_db`
3. Check firewall: `Test-NetConnection -ComputerName localhost -Port 5432`

### MQTT Connection Failed
```
❌ Error: Failed to connect to MQTT broker
```
**Fix:**
1. Test broker: `mosquitto_sub -h mqtt.example.com -t test -v`
2. Check credentials in config
3. Verify port (1883 or 8883)
4. Check TLS settings if using port 8883

### Tag Not Found
```
❌ Error: Tag 'TAG001' not found in tag_master
```
**Fix:**
1. Check tag exists: 
   ```sql
   SELECT * FROM historian_meta.tag_master WHERE tag_id = 'TAG001';
   ```
2. Ensure `is_active = true`
3. Wait for cache refresh (5 minutes) or restart service

### High Processing Time
```
⚠ Warning: Processing time 500ms exceeds threshold
```
**Fix:**
1. Increase worker_threads in config (e.g., 16)
2. Check database performance
3. Add indexes:
   ```sql
   CREATE INDEX idx_timeseries_time ON historian_raw.historian_timeseries(time DESC);
   ```

---

## 📈 Monitoring

### Log Files
```
logs/mqtt_subscriber_service.log        # Main log
logs/mqtt_subscriber_service_error.log  # Errors only
```

### Key Metrics (logged every 60 seconds)
```
Messages:
  - Received: Total messages from MQTT
  - Processed: Successfully processed
  - Failed: Processing failures
  - Rate: Messages per second
  - Success Rate: Percentage

Processing:
  - Avg Time: Average processing time (ms)
  - Min/Max Time: Range (ms)

Database:
  - Inserts: Successful inserts
  - Insert Errors: Failed inserts
  - Total Records: Records inserted
```

### Health Status
```batch
python scripts\health_check.py
```

**Possible Statuses:**
- ✓ HEALTHY - All components operational
- ⚠ DEGRADED - Some components unhealthy
- ✗ UNHEALTHY - Critical components down

---

## 🔐 Security

### Enable TLS
```yaml
security:
  enable_tls: true
  tls:
    ca_cert: C:\certs\ca.crt
    client_cert: C:\certs\client.crt
    client_key: C:\certs\client.key
```

### Use Environment Variables
```batch
# Set in environment
set DB_PASSWORD=your_secure_password
set MQTT_PASSWORD=your_mqtt_password

# Or create set_environment.bat
@echo off
set DB_PASSWORD=your_secure_password
set MQTT_PASSWORD=your_mqtt_password
```

### Input Sanitization (Default: Enabled)
Protects against:
- SQL injection
- Command injection
- XSS attacks

---

## 📝 Database Schema

### Key Tables

#### mqtt_topic_config
```sql
-- MQTT topic configurations
topic_id SERIAL PRIMARY KEY
topic_name VARCHAR(255) UNIQUE
qos INTEGER
enabled BOOLEAN
```

#### mqtt_audit_main
```sql
-- Main audit records
audit_id SERIAL PRIMARY KEY
message_id VARCHAR(100) UNIQUE
topic VARCHAR(255)
status VARCHAR(20)
received_at TIMESTAMP
```

#### mqtt_audit_history
```sql
-- Processing step history
history_id SERIAL PRIMARY KEY
audit_id INTEGER REFERENCES mqtt_audit_main
step VARCHAR(50)
status VARCHAR(20)
details TEXT
```

#### historian_timeseries
```sql
-- Time-series data
time TIMESTAMP NOT NULL
tag_id VARCHAR(100) NOT NULL
value_num DOUBLE PRECISION
value_text TEXT
value_bool BOOLEAN
quality CHAR(1)
```

---

## 🛠️ Performance Tuning

### For High Throughput (>100 msg/s)
```yaml
processing:
  worker_threads: 16
  task_queue_size: 5000

database:
  pool_max_connections: 30
```

### For Low Latency (<10ms)
```yaml
processing:
  worker_threads: 4
  task_queue_size: 100

database:
  pool_max_connections: 10
```

### For Memory Constrained (<256MB)
```yaml
processing:
  worker_threads: 4
  task_queue_size: 500

database:
  pool_max_connections: 10
```

---

## 📞 Support Checklist

Before contacting support, collect:

1. **Error Logs**
   ```batch
   type logs\mqtt_subscriber_service_error.log
   ```

2. **Configuration**
   ```batch
   type config\service_config.yaml
   ```

3. **Health Status**
   ```batch
   python scripts\health_check.py
   ```

4. **Database Status**
   ```sql
   SELECT COUNT(*) FROM historian_raw.mqtt_audit_main;
   SELECT status, COUNT(*) FROM historian_raw.mqtt_audit_main GROUP BY status;
   ```

5. **Service Metrics** (from logs)
   ```batch
   findstr /C:"Metrics" logs\mqtt_subscriber_service.log
   ```

---

## 📚 Additional Resources

- **Full Documentation:** [README.md](README.md)
- **Deployment Guide:** [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)
- **Implementation Details:** [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md)
- **Test Plan:** [TEST_PLAN.md](TEST_PLAN.md)

---

## 🔑 Key File Locations

```
mqtt_subscriber_service/
├── config/
│   ├── service_config.yaml     ← Main configuration
│   └── logging_config.json     ← Logging settings
├── sql/
│   └── create_subscriber_tables.sql  ← Database setup
├── logs/
│   ├── mqtt_subscriber_service.log   ← Application log
│   └── mqtt_subscriber_service_error.log  ← Error log
├── scripts/
│   └── health_check.py         ← Health check utility
├── run_service.bat             ← Start service
└── install.bat                 ← Installation script
```

---

**Quick Reference Version:** 1.0  
**Last Updated:** 2024-01-15
