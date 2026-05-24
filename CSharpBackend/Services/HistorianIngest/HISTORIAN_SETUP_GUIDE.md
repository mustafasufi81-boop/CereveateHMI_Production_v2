# Historian Ingest System - Setup Guide

## Overview
The Historian Ingest System collects OPC DA data, applies frequency filtering (1s-60s per tag), and writes to TimescaleDB using high-performance binary COPY.

## Architecture
```
OPC Events → RateController (change + frequency filter) → Batcher (sharded) → DbWriter (COPY binary) → TimescaleDB
                                                                    ↓ (on failure)
                                                               SpoolManager (disk failover)
```

## Setup Steps

### 1. Install TimescaleDB
```bash
# Install PostgreSQL 15+ with TimescaleDB extension
# Windows: Download from https://www.timescale.com/
# Enable extension:
CREATE EXTENSION IF NOT EXISTS timescaledb;
```

### 2. Run Database Migration
```bash
psql -U postgres -d historian -f Services/HistorianIngest/DB/schema_migration.sql
```

This creates:
- `historian_meta` - Tag mappings (tag_master table)
- `historian_raw` - Timeseries hypertable + latest_values
- `historian_admin` - Checkpoints, spool tracking, events
- `historian_mon` - System metrics

### 3. Configure appsettings.json
Update connection string in `appsettings.json`:
```json
{
  "Historian": {
    "Database": {
      "ConnectionString": "Host=localhost;Port=5432;Database=historian;Username=postgres;Password=YOUR_PASSWORD"
    }
  }
}
```

### 4. Install NuGet Packages
```bash
dotnet add package Npgsql --version 8.0.0
dotnet add package Npgsql.NodaTime --version 8.0.0
```

### 5. Add Sample Tag Mappings
Use the UI or API to add tags:

**UI**: Navigate to `http://localhost:5001/historian/mapping.html`

**API**:
```bash
curl -X POST http://localhost:5001/api/historian/mapping \
  -H "Content-Type: application/json" \
  -d '{
    "tagId": "TAG001",
    "tagName": "Turbine Speed",
    "dataType": "double",
    "dbLoggingIntervalMs": 1000,
    "enabled": true
  }'
```

### 6. Start Application
```bash
dotnet run
```

Check logs for:
```
HistorianIngestHostedService starting...
MappingCacheService initialized with X tags, version Y
Subscribed to OPC TagValuesUpdated events
```

### 7. Monitor System

**Dashboard**: `http://localhost:5001/historian/dashboard.html`
- Real-time metrics (refreshes every 3s)
- Rate control stats
- Batch throughput
- Spool queue depth

**Events Log**: `http://localhost:5001/historian/events.html`
- All system events
- Filter by type/tag
- Troubleshooting errors

**Health Endpoints**:
- `/api/historian/health/live` - Liveness probe
- `/api/historian/health/ready` - Readiness (checks DB)
- `/api/historian/metrics` - Prometheus metrics

## Key Features

### Per-Tag Frequency Control
Each tag has configurable `db_logging_interval_ms` (1000-60000):
- **1000ms** = log every second (high-speed tags)
- **5000ms** = log every 5 seconds (slow sensors)
- **60000ms** = log every minute (status flags)

### Change Detection
Only logs when value changes beyond `deadband_value`:
- Prevents DB spam from noisy sensors
- Reduces writes by 50-95% for stable processes

### Spool Failover
When database unreachable:
- Batches written to `D:\HistorianSpool\*.ready`
- Auto-replay when DB restored
- Idempotent (SHA256 hash prevents duplicates)

### Sharded Batching
8 parallel writer shards by default:
- Sustains 50k-300k samples/sec depending on hardware
- COPY binary format (10x faster than INSERT)

## Configuration Reference

### Tag Mapping Fields
- `tag_id` (PK) - Unique identifier
- `data_type` - double | int | bool | string
- `db_logging_interval_ms` - **1000 to 60000** (enforced)
- `deadband_value` - Change threshold for analog values
- `enabled` - false = drop all incoming samples
- `mapping_version` - Auto-incremented on update

### Writer Config
- `ShardCount` - Parallel writer threads (4-32)
- `CheckpointIntervalSeconds` - Restart recovery frequency
- `MaxRows` / `MaxBytes` / `MaxWaitMs` - Batch triggers

### Spool Config
- `SpoolDirectory` - Disk path for failed batches
- `MaxSpoolSizeMB` - Safety limit (10GB default)
- `AutoReplay` - Enable/disable automatic recovery

## Troubleshooting

### No data in database
1. Check mapping cache: `GET /api/historian/mapping`
2. Verify tag enabled: `enabled = true`
3. Check OPC connection: Existing OPC UI
4. View events: `/api/historian/events?eventType=unmapped_tag`

### High filter ratio
- Normal if `db_logging_interval_ms` > OPC scan rate
- Example: OPC sends 1000/sec, DB interval 1000ms → 99.9% filtered (expected)

### Spool queue growing
1. Check DB health: `/api/historian/health/ready`
2. Verify connection string
3. Check PostgreSQL logs
4. Increase batch size or shard count

### Mapping not updating
- Cache refreshes automatically via pg_notify
- Manual refresh: `POST /api/historian/mapping/refresh`
- Check PostgreSQL LISTEN/NOTIFY working

## API Endpoints

### Tag Mapping
- `GET /api/historian/mapping` - List all tags
- `GET /api/historian/mapping/{tagId}` - Get specific tag
- `POST /api/historian/mapping` - Create/update tag
- `DELETE /api/historian/mapping/{tagId}` - Delete tag
- `POST /api/historian/mapping/refresh` - Force cache refresh

### Events
- `GET /api/historian/events?eventType=X&tagId=Y&limit=100`

### Health
- `GET /api/historian/health/live`
- `GET /api/historian/health/ready`
- `GET /api/historian/metrics` (Prometheus)
- `GET /api/historian/dashboard` (JSON summary)

## Database Queries

### Check tag count
```sql
SELECT COUNT(*) FROM historian_meta.tag_master WHERE enabled = true;
```

### View latest values
```sql
SELECT * FROM historian_raw.historian_latest_value ORDER BY time DESC LIMIT 10;
```

### Query historical data
```sql
SELECT time, tag_id, value_num, quality
FROM historian_raw.historian_timeseries
WHERE tag_id = 'TAG001'
  AND time > NOW() - INTERVAL '1 hour'
ORDER BY time DESC;
```

### Check spool applied
```sql
SELECT * FROM historian_admin.spool_applied ORDER BY applied_at DESC;
```

### View events
```sql
SELECT event_time, event_type, tag_id, severity, message
FROM historian_admin.historian_events
ORDER BY event_time DESC LIMIT 50;
```

## Performance Tuning

### For 10k+ tags
- Increase `ShardCount` to 16-32
- Use PgBouncer (transaction pooling)
- Enable TimescaleDB compression (7+ days)

### For high frequency (1s interval)
- Increase `MaxRows` to 20000
- Reduce `MaxWaitMs` to 1000
- Monitor CPU/memory

### For unreliable networks
- Increase `MaxRetries` to 5
- Increase `RetryDelayMs` to 2000
- Enable spool with larger `MaxSpoolSizeMB`

## Notes
- **NO CHANGES TO OPC CODE** - Historian subscribes to existing `TagValuesUpdated` event
- **NO PARQUET IMPACT** - Existing DataLoggingService untouched
- **MAPPING_VERSION CRITICAL** - Never manually modify, always use API/UI
