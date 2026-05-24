# Valid Event Types for historian_events Table

## Database Constraint
The `historian_events` table has a check constraint on the `event_type` column:

```sql
event_type ~ '^(SYSTEM|WRITER|DATA_QUALITY|ALARM|TRIP|USER|AUDIT)_[A-Z_0-9]+$'::text
```

## Valid Event Type Format

Event types MUST follow this pattern:
- Start with one of these prefixes: `SYSTEM_`, `WRITER_`, `DATA_QUALITY_`, `ALARM_`, `TRIP_`, `USER_`, `AUDIT_`
- Followed by uppercase letters, underscores, or numbers

## Examples of Valid Event Types

### ALARM Events
- `ALARM_HIGH_CRITICAL` - Critical high alarm
- `ALARM_HIGH_WARNING` - Warning level high alarm
- `ALARM_LOW_CRITICAL` - Critical low alarm
- `ALARM_LOW_WARNING` - Warning level low alarm
- `ALARM_ACTIVATED` - Alarm activated
- `ALARM_ACKNOWLEDGED` - Alarm acknowledged
- `ALARM_CLEARED` - Alarm cleared
- `ALARM_RATE_OF_CHANGE` - Rate of change alarm
- `ALARM_DEVIATION` - Deviation alarm

### TRIP Events
- `TRIP_EMERGENCY_STOP` - Emergency stop triggered
- `TRIP_SAFETY_INTERLOCK` - Safety interlock trip
- `TRIP_OVERLOAD` - Overload protection trip
- `TRIP_SEQUENCE_FAULT` - Sequence fault trip

### SYSTEM Events
- `SYSTEM_STARTUP` - System startup
- `SYSTEM_SHUTDOWN` - System shutdown
- `SYSTEM_CONFIG_CHANGE` - Configuration changed
- `SYSTEM_CONNECTION_LOST` - Connection lost
- `SYSTEM_CONNECTION_RESTORED` - Connection restored

### DATA_QUALITY Events
- `DATA_QUALITY_BAD` - Data quality degraded to bad
- `DATA_QUALITY_UNCERTAIN` - Data quality uncertain
- `DATA_QUALITY_GOOD` - Data quality restored to good
- `DATA_QUALITY_TIMEOUT` - Data read timeout

### USER Events
- `USER_LOGIN` - User login
- `USER_LOGOUT` - User logout
- `USER_ACTION` - User performed action
- `USER_OVERRIDE` - User override

### AUDIT Events
- `AUDIT_SETPOINT_CHANGE` - Setpoint changed
- `AUDIT_MODE_CHANGE` - Mode changed
- `AUDIT_PARAMETER_CHANGE` - Parameter changed

### WRITER Events
- `WRITER_SUCCESS` - Write operation succeeded
- `WRITER_FAILED` - Write operation failed
- `WRITER_RETRY` - Write operation retry

## Invalid Examples (Will Fail Constraint)

❌ `HIGH_ALARM_CRITICAL` - Wrong order, prefix must come first
❌ `ALARM-HIGH-CRITICAL` - Hyphens not allowed
❌ `alarm_high_critical` - Must be uppercase
❌ `ALARM` - Missing suffix after underscore
❌ `WARNING_HIGH` - Invalid prefix (WARNING not in allowed list)

## Fixed Event Types in Code

All test files and sample data have been updated:

| Old (Invalid) | New (Valid) |
|---------------|-------------|
| `HIGH_ALARM_CRITICAL` | `ALARM_HIGH_CRITICAL` |
| `HIGH_ALARM_WARNING` | `ALARM_HIGH_WARNING` |

## Files Updated
- ✅ `latest_sample_mqtt_data.json`
- ✅ `tests/generate_test_data.py`
- ✅ `test_mqtt_data_process.py`

---
*Updated: January 10, 2026*
