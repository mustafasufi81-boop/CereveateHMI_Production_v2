# Database Deployment - Quick Reference

## 📦 Files Created

### SQL Scripts
1. **deploy_all_tables.sql** - Complete deployment (all tables, indexes, sample data)
2. **create_user.sql** - Create mqtt_subscriber_user with permissions
3. **verify_deployment.sql** - Verification and status checks
4. **create_subscriber_tables.sql** - MQTT subscriber tables only (original)

### Batch Scripts
1. **deploy_database.bat** - Windows deployment script

### Documentation
1. **DATABASE_DEPLOYMENT.md** - Complete deployment guide

## ⚡ Quick Start

### Method 1: Automated (Recommended)
```batch
cd mqtt_subscriber_service
deploy_database.bat
```

### Method 2: Manual Steps
```bash
# 1. Deploy all tables
psql -h localhost -U cereveate -d cerevatedb -f sql/deploy_all_tables.sql

# 2. Create service user (as postgres superuser)
psql -h localhost -U postgres -d cerevatedb -f sql/create_user.sql

# 3. Verify deployment
psql -h localhost -U cereveate -d cerevatedb -f sql/verify_deployment.sql
```

## 📊 Tables Created

### Schemas
- `historian_meta` - Configuration data
- `historian_raw` - Time-series and audit data

### Tables (5 New + 2 Existing)

**New MQTT Subscriber Tables:**
1. ✅ `mqtt_topic_config` - Topic subscriptions
2. ✅ `mqtt_audit_main` - Message audit (main)
3. ✅ `mqtt_audit_history` - Processing steps
4. ✅ `historian_events` - Alarms/events (**NEW for Phase 6**)

**Existing Historian Tables (Enhanced):**
5. ✅ `historian_timeseries` - Sensor data
6. ✅ `tag_master` - Tag metadata

## 🔑 Key Features

### 1. Batch Message Support
- Handles `values` array with multiple tags
- Processes `samples` array (historical data points)
- Extracts metadata: plcId, dataType, scanRateMs

### 2. Alarm Processing
- **historian_events** table with severity levels
- Metadata storage (setpoint, plant, area, equipment)
- Acknowledgment and clear tracking
- Indexed for fast active alarm queries

### 3. Audit Trail
- Message-level tracking (audit_main)
- Step-by-step history (audit_history)
- Processing duration metrics
- Error tracking

### 4. TimescaleDB Ready
- Optional hypertable conversion
- Automatic time-based partitioning
- Optimized for time-series queries

## ✅ Verification Checklist

After deployment, verify:

- [ ] All 6 tables exist in historian_raw
- [ ] tag_master exists in historian_meta
- [ ] Sample MQTT topics inserted (5 rows)
- [ ] Indexes created (20+ indexes)
- [ ] User mqtt_subscriber_user created
- [ ] Permissions granted correctly
- [ ] Database connection test passes

## 🔐 Security

**mqtt_subscriber_user** has:
- ✅ READ: topic_config, tag_master
- ✅ INSERT: timeseries, events, audit tables
- ✅ UPDATE: audit_main, events (for acknowledgment)
- ❌ NO DELETE permissions
- ❌ NO schema modifications

## 📈 Sample Queries

### Insert test timeseries data
```sql
INSERT INTO historian_raw.historian_timeseries 
(time, tag_id, value_num, quality, sample_source, mapping_version)
VALUES 
(NOW(), 'TEST_TAG_001', 25.5, 'G', 'MQTT', 1);
```

### Insert test alarm
```sql
INSERT INTO historian_raw.historian_events
(time, tag_id, event_type, severity, message, metadata)
VALUES (
    NOW(),
    'TEST_TAG_001',
    'HIGH_ALARM_WARNING',
    2,
    'Test alarm triggered',
    '{"setpoint": 20.0, "alarm_value": 25.5}'::jsonb
);
```

### Check recent messages
```sql
SELECT message_id, topic_name, status, records_inserted
FROM historian_raw.mqtt_audit_main
ORDER BY first_received_time DESC
LIMIT 5;
```

## 🆘 Troubleshooting

| Issue | Solution |
|-------|----------|
| "psql not found" | Add PostgreSQL bin to PATH |
| "permission denied" | Run create_user.sql as superuser |
| "relation already exists" | Tables created, run verify script |
| "connection refused" | Check PostgreSQL service running |

## 📝 Next Steps

1. ✅ Run deployment script
2. ✅ Create database user
3. ✅ Update config/config.yaml
4. ✅ Add MQTT topics to mqtt_topic_config
5. ✅ Test with: `python tests/test_basic.py`
6. ✅ Start service: `python src/service_main.py`

---

**Status**: Database layer complete and ready for testing! ✅
