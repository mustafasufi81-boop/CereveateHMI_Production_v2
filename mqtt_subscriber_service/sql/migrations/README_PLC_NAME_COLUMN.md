# PLC Name Column Addition to mqtt_topic_config

## Overview
Added `plc_name` column to the `historian_raw.mqtt_topic_config` table to track which PLC each MQTT topic is associated with. Each PLC is assigned a unique topic name for better organization and routing.

## Changes Made

### Database Schema Changes

1. **Added Column**: `plc_name TEXT NOT NULL`
   - Purpose: Identify which PLC the topic belongs to
   - Constraint: NOT NULL (required field)
   - Index: Created `idx_mqtt_topic_plc_name` for query optimization

### Updated Files

1. **Schema Definition Files**:
   - `mqtt_subscriber_service/sql/deploy_all_tables.sql`
   - `mqtt_subscriber_service/sql/create_subscriber_tables.sql`

2. **Application Code**:
   - `mqtt_subscriber_service/src/cache/topic_cache.py` - Updated to fetch and cache plc_name

3. **Migration Script**:
   - `mqtt_subscriber_service/sql/migrations/add_plc_name_column.sql` - For existing databases

## Migration Instructions

### For New Deployments
Simply run the updated schema files:
```bash
psql -U postgres -d Historian_data -f mqtt_subscriber_service/sql/create_subscriber_tables.sql
```

### For Existing Databases
Run the migration script:
```bash
psql -U postgres -d Historian_data -f mqtt_subscriber_service/sql/migrations/add_plc_name_column.sql
```

**Important**: After running the migration, review and update any topics with `plc_name = 'PLC_UNKNOWN'` to match your actual PLC configuration.

## Usage Examples

### Insert New Topic with PLC Name
```sql
INSERT INTO historian_raw.mqtt_topic_config 
(topic_name, plc_name, qos, is_active, thread_group) 
VALUES 
('production/line_1/data', 'PLC_LINE_1', 1, TRUE, 1);
```

### Query Topics by PLC
```sql
SELECT * FROM historian_raw.mqtt_topic_config 
WHERE plc_name = 'PLC_PLANT_A_001';
```

### Update PLC Name for Existing Topic
```sql
UPDATE historian_raw.mqtt_topic_config 
SET plc_name = 'PLC_MAIN_001' 
WHERE topic_name = 'plant/gateway/data';
```

## PLC Naming Convention

Recommended naming format: `PLC_<LOCATION>_<NUMBER>`

Examples:
- `PLC_PLANT_A_001` - Plant A, PLC #1
- `PLC_PLANT_B_002` - Plant B, PLC #2
- `PLC_GATEWAY_01` - Gateway PLC #1
- `PLC_SENSORS_01` - Sensor PLC #1
- `PLC_LINE_1` - Production Line 1

## Application Impact

### Topic Cache
The `topic_cache.py` now includes `plc_name` in the cached topic information:
```python
{
    'topic_id': 1,
    'topic_name': 'plant/gateway/data',
    'plc_name': 'PLC_GATEWAY_01',
    'qos': 1,
    'is_active': True,
    'processing_rules': None
}
```

### Benefits
1. **Better Organization**: Group topics by PLC for easier management
2. **Routing**: Enable PLC-specific message routing and processing
3. **Monitoring**: Track which PLC is generating traffic
4. **Scalability**: Support for multi-PLC environments

## Verification

After deployment, verify the changes:
```sql
-- Check column exists
SELECT column_name, data_type, is_nullable 
FROM information_schema.columns 
WHERE table_schema = 'historian_raw' 
  AND table_name = 'mqtt_topic_config'
  AND column_name = 'plc_name';

-- Check all topics have PLC assignments
SELECT topic_name, plc_name, is_active 
FROM historian_raw.mqtt_topic_config 
ORDER BY plc_name, topic_name;
```

## Rollback (if needed)

To rollback this change:
```sql
ALTER TABLE historian_raw.mqtt_topic_config DROP COLUMN IF EXISTS plc_name;
DROP INDEX IF EXISTS historian_raw.idx_mqtt_topic_plc_name;
```

**Note**: Rollback will result in loss of PLC assignment data.
