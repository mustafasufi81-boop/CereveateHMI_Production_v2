# MQTT Subscriber Service - Database Deployment Guide

This guide covers the complete database setup for the MQTT Subscriber Service.

## 📋 Prerequisites

- PostgreSQL 14+ installed
- Database `cerevatedb` already created
- PostgreSQL superuser access (for creating user)
- `psql` command-line tool in PATH

## 🗂️ Database Structure

The service uses 3 PostgreSQL schemas:

### `historian_meta` Schema
- **tag_master** - Tag configuration and metadata

### `historian_raw` Schema
- **historian_timeseries** - Time-series sensor data
- **historian_events** - Alarm and event data
- **mqtt_topic_config** - MQTT topic subscriptions
- **mqtt_audit_main** - Message processing audit (main)
- **mqtt_audit_history** - Detailed processing steps

### `historian_admin` Schema (Optional)
- **spool_applied** - Batch import tracking
- **writer_checkpoints** - Writer state tracking
- **events** - System events log

## 🚀 Quick Deployment

### Option 1: Using Batch Script (Windows)

```batch
cd mqtt_subscriber_service
deploy_database.bat
```

This will:
1. Prompt for database credentials
2. Run deployment SQL script
3. Create all tables and indexes
4. Insert sample topic configurations
5. Verify deployment

### Option 2: Using psql Directly

```bash
# Navigate to SQL directory
cd mqtt_subscriber_service/sql

# Run deployment script
psql -h localhost -p 5432 -U cereveate -d cerevatedb -f deploy_all_tables.sql

# Verify deployment
psql -h localhost -p 5432 -U cereveate -d cerevatedb -f verify_deployment.sql
```

## 👤 Create Service User

The service requires a dedicated database user with limited permissions.

### Step 1: Create User (as superuser)

```bash
psql -h localhost -p 5432 -U postgres -d cerevatedb -f sql/create_user.sql
```

Default credentials created:
- **Username**: `mqtt_subscriber_user`
- **Password**: `MqttSub$ecure2026!` ⚠️ **CHANGE THIS!**

### Step 2: Change Default Password

```sql
ALTER USER mqtt_subscriber_user WITH PASSWORD 'your_secure_password_here';
```

### Step 3: Update Configuration

Update `config/config.yaml`:

```yaml
database:
  host: localhost
  port: 5432
  database: cerevatedb
  user: mqtt_subscriber_user
  password: your_secure_password_here
```

## 📊 Table Details

### 1. mqtt_topic_config
**Purpose**: Configure which MQTT topics to subscribe to

| Column | Type | Description |
|--------|------|-------------|
| topic_id | SERIAL | Primary key |
| topic_name | TEXT | MQTT topic pattern (supports # wildcards) |
| qos | INTEGER | Quality of Service (0, 1, or 2) |
| is_active | BOOLEAN | Enable/disable subscription |
| thread_group | INTEGER | Worker thread group assignment |
| processing_rules | JSONB | Optional custom rules |

**Sample Data**:
```sql
INSERT INTO historian_raw.mqtt_topic_config (topic_name, qos, is_active) VALUES
('plant/gateway/data', 1, TRUE),
('plant/sensors/#', 1, TRUE);
```

### 2. mqtt_audit_main
**Purpose**: Main audit record for each MQTT message

| Column | Type | Description |
|--------|------|-------------|
| audit_id | BIGSERIAL | Primary key |
| message_id | TEXT | Unique message identifier |
| topic_name | TEXT | MQTT topic received from |
| payload_size | INTEGER | Payload size in bytes |
| status | TEXT | processing, completed, failed |
| records_inserted | INTEGER | Total records inserted |
| processing_duration_ms | INTEGER | Processing time |

### 3. mqtt_audit_history
**Purpose**: Detailed processing step tracking

| Column | Type | Description |
|--------|------|-------------|
| hist_id | BIGSERIAL | Primary key |
| audit_id | BIGINT | References audit_main |
| step | TEXT | Step name (parse, validate, insert) |
| status | TEXT | success or failed |
| details | TEXT | Additional information |

### 4. historian_timeseries
**Purpose**: Store sensor time-series data

| Column | Type | Description |
|--------|------|-------------|
| id | BIGSERIAL | Primary key |
| time | TIMESTAMPTZ | Sample timestamp |
| tag_id | TEXT | Tag identifier |
| value_num | DOUBLE PRECISION | Numeric value |
| value_bool | BOOLEAN | Boolean value |
| value_text | TEXT | Text value |
| quality | TEXT | Data quality code (G=Good) |
| sample_source | TEXT | Data source (MQTT, OPC, etc.) |

**Indexes**:
- `idx_historian_timeseries_tag_time` - Fast tag queries
- `idx_historian_timeseries_time` - Time-based queries

### 5. historian_events
**Purpose**: Store alarm and event data

| Column | Type | Description |
|--------|------|-------------|
| event_id | BIGSERIAL | Primary key |
| time | TIMESTAMPTZ | Event timestamp |
| tag_id | TEXT | Tag identifier |
| event_type | TEXT | Event type (HIGH_ALARM_CRITICAL, etc.) |
| severity | INTEGER | 1=Critical, 2=Warning, 3=Info |
| message | TEXT | Event description |
| metadata | JSONB | Additional data (setpoint, plant, area, etc.) |
| acknowledged | BOOLEAN | Acknowledgment status |
| cleared | BOOLEAN | Clear status |

**Indexes**:
- `idx_historian_events_tag_time` - Tag event history
- `idx_historian_events_severity` - Filter by severity
- `idx_historian_events_active` - Active alarms only

## 🔐 Security Permissions

The `mqtt_subscriber_user` has these permissions:

### READ-ONLY Access
- ✅ `historian_raw.mqtt_topic_config` (SELECT)
- ✅ `historian_meta.tag_master` (SELECT)

### INSERT Access
- ✅ `historian_raw.mqtt_audit_main` (INSERT, UPDATE)
- ✅ `historian_raw.mqtt_audit_history` (INSERT)
- ✅ `historian_raw.historian_timeseries` (INSERT)
- ✅ `historian_raw.historian_events` (INSERT, UPDATE)

### No Access
- ❌ DELETE operations on any table
- ❌ Schema modifications
- ❌ Other schemas/databases

## ⏱️ TimescaleDB (Optional)

For better performance with large time-series datasets, enable TimescaleDB:

```sql
-- Create extension (as superuser)
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Convert tables to hypertables
SELECT create_hypertable(
    'historian_raw.historian_timeseries', 
    'time',
    chunk_time_interval => INTERVAL '1 day'
);

SELECT create_hypertable(
    'historian_raw.historian_events', 
    'time',
    chunk_time_interval => INTERVAL '7 days'
);
```

**Benefits**:
- Automatic data partitioning by time
- Optimized time-series queries
- Built-in compression support
- Improved INSERT performance

## ✅ Verification

Run verification script to check deployment:

```bash
psql -h localhost -p 5432 -U cereveate -d cerevatedb -f sql/verify_deployment.sql
```

This checks:
- ✅ All schemas exist
- ✅ All tables created
- ✅ Indexes created
- ✅ Constraints in place
- ✅ Sample data inserted
- ✅ User permissions granted
- ✅ TimescaleDB status

## 🧪 Test Database Connection

```python
# Test from Python
cd mqtt_subscriber_service
python

>>> from src.database.db_connection import DatabaseConnection
>>> config = {
...     'host': 'localhost',
...     'port': 5432,
...     'database': 'cerevatedb',
...     'user': 'mqtt_subscriber_user',
...     'password': 'your_password'
... }
>>> db = DatabaseConnection(config)
>>> db.connect()
>>> print("✅ Database connection successful!")
>>> db.disconnect()
```

## 📈 Monitoring Queries

### Check recent messages
```sql
SELECT 
    message_id,
    topic_name,
    status,
    records_inserted,
    processing_duration_ms,
    first_received_time
FROM historian_raw.mqtt_audit_main
ORDER BY first_received_time DESC
LIMIT 10;
```

### Check processing failures
```sql
SELECT 
    message_id,
    topic_name,
    error_message,
    first_received_time
FROM historian_raw.mqtt_audit_main
WHERE status = 'failed'
ORDER BY first_received_time DESC;
```

### Check active alarms
```sql
SELECT 
    tag_id,
    event_type,
    severity,
    message,
    time
FROM historian_raw.historian_events
WHERE NOT acknowledged OR NOT cleared
ORDER BY severity, time DESC;
```

### Check topic subscription status
```sql
SELECT 
    topic_name,
    is_active,
    qos,
    thread_group
FROM historian_raw.mqtt_topic_config
ORDER BY topic_name;
```

## 🔧 Maintenance

### Clean old audit records (retention policy)
```sql
-- Delete audit records older than 30 days
DELETE FROM historian_raw.mqtt_audit_main
WHERE first_received_time < NOW() - INTERVAL '30 days';
```

### Analyze table statistics
```sql
ANALYZE historian_raw.historian_timeseries;
ANALYZE historian_raw.historian_events;
ANALYZE historian_raw.mqtt_audit_main;
```

### Check table sizes
```sql
SELECT 
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
WHERE schemaname IN ('historian_raw', 'historian_meta')
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
```

## 🆘 Troubleshooting

### Issue: "permission denied for schema"
**Solution**: Run `sql/create_user.sql` to grant proper permissions

### Issue: "relation already exists"
**Solution**: Tables already created. Run `sql/verify_deployment.sql` to check status

### Issue: "could not connect to server"
**Solution**: 
1. Verify PostgreSQL is running: `pg_isready`
2. Check connection parameters in script
3. Verify firewall settings

### Issue: "password authentication failed"
**Solution**: Verify credentials in `config/config.yaml` match database user

## 📝 Next Steps

After successful database deployment:

1. ✅ Verify all tables created
2. ✅ Create service user with secure password
3. ✅ Update `config/config.yaml` with credentials
4. ✅ Configure MQTT topics in `mqtt_topic_config`
5. ✅ Add tags to `tag_master` table
6. ✅ Run service tests: `python tests/test_basic.py`
7. ✅ Start MQTT Subscriber Service

## 📚 Related Documentation

- [Installation Guide](INSTALLATION_GUIDE.md)
- [Configuration Guide](CONFIGURATION_GUIDE.md)
- [Service Architecture](ARCHITECTURE.md)
- [API Documentation](API_DOCUMENTATION.md)

---

**Note**: Always backup your database before running deployment scripts in production!
