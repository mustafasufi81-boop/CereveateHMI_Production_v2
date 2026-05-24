# Alarm Audit Trail API Quick Reference

## Base URL
```
http://localhost:6001/api/alarms
```

## Endpoints

### 1. Get Audit Trail for Specific Alarm
```http
GET /api/alarms/audit/<alarm_id>
```

**Parameters:**
- `alarm_id` (path, required) - Event ID of the alarm

**Response:**
```json
{
  "success": true,
  "alarm_id": 12345,
  "audit_trail": [
    {
      "audit_id": 1,
      "event_id": 12345,
      "tag_id": "Pump_01_Pressure",
      "tag_name": "Pump 01 Discharge Pressure",
      "event_type": "ALARM_HIGH_CRITICAL",
      "action_type": "RAISED",
      "action_timestamp": "2026-01-28T10:00:00Z",
      "performed_by": "SYSTEM",
      "previous_state": null,
      "new_state": "ACTIVE",
      "alarm_priority": 5,
      "priority_label": "CRITICAL",
      "alarm_actual_value": 125.5,
      "alarm_setpoint": 100.0,
      "minutes_since_previous_action": null,
      "response_time_seconds": null
    },
    {
      "audit_id": 2,
      "event_id": 12345,
      "action_type": "ACKNOWLEDGED",
      "action_timestamp": "2026-01-28T10:02:30Z",
      "performed_by": "operator",
      "previous_state": "ACTIVE",
      "new_state": "ACKNOWLEDGED",
      "action_notes": "Investigating cause",
      "minutes_since_previous_action": 2.5,
      "response_time_seconds": 150
    }
  ],
  "count": 2
}
```

**Example:**
```bash
curl http://localhost:6001/api/alarms/audit/12345
```

---

### 2. Get Audit Trail for Tag
```http
GET /api/alarms/audit/tag/<tag_id>?limit=100
```

**Parameters:**
- `tag_id` (path, required) - Tag identifier
- `limit` (query, optional) - Max records to return (default: 100)

**Response:**
```json
{
  "success": true,
  "tag_id": "Pump_01_Pressure",
  "audit_trail": [
    { "audit_id": 10, ... },
    { "audit_id": 9, ... },
    { "audit_id": 8, ... }
  ],
  "count": 15
}
```

**Example:**
```bash
curl "http://localhost:6001/api/alarms/audit/tag/Pump_01_Pressure?limit=50"
```

---

### 3. Get Operator Statistics
```http
GET /api/alarms/audit/operator/<operator_name>/stats?days=7
```

**Parameters:**
- `operator_name` (path, required) - Operator username
- `days` (query, optional) - Number of days to look back (default: 7)

**Response:**
```json
{
  "success": true,
  "operator": "john_smith",
  "days": 7,
  "stats": {
    "performed_by": "john_smith",
    "total_actions": 45,
    "acks_count": 30,
    "clears_count": 15,
    "avg_ack_response_minutes": 2.5,
    "fastest_ack_minutes": 0.5,
    "slowest_ack_minutes": 8.2
  }
}
```

**Example:**
```bash
curl "http://localhost:6001/api/alarms/audit/operator/john_smith/stats?days=7"
```

---

### 4. Get Unacknowledged Alarms
```http
GET /api/alarms/audit/unacknowledged?hours=24
```

**Parameters:**
- `hours` (query, optional) - Hours to look back (default: 24)

**Response:**
```json
{
  "success": true,
  "hours": 24,
  "unacknowledged_alarms": [
    {
      "event_id": 12350,
      "tag_id": "Turbine_Vibration",
      "tag_name": "Turbine Bearing Vibration",
      "event_type": "ALARM_HIGH_CRITICAL",
      "raised_at": "2026-01-28T15:30:00Z",
      "alarm_priority": 5,
      "priority_label": "CRITICAL",
      "alarm_actual_value": 8.5,
      "alarm_setpoint": 5.0,
      "minutes_since_raised": 45.5
    }
  ],
  "count": 1
}
```

**Example:**
```bash
curl "http://localhost:6001/api/alarms/audit/unacknowledged?hours=48"
```

---

## Error Responses

### Database Not Available
```json
{
  "success": false,
  "error": "Database not available",
  "audit_trail": []
}
```
**Status:** 503 Service Unavailable

### Audit Module Not Available
```json
{
  "success": false,
  "error": "Alarm audit trail module not available",
  "audit_trail": []
}
```
**Status:** 503 Service Unavailable

### General Error
```json
{
  "success": false,
  "error": "Error message here",
  "audit_trail": []
}
```
**Status:** 500 Internal Server Error

---

## Response Fields

### Audit Record Fields

| Field | Type | Description |
|-------|------|-------------|
| `audit_id` | int | Unique audit record ID |
| `event_id` | int | Reference to alarm event |
| `tag_id` | string | Process tag identifier |
| `tag_name` | string | Human-readable tag name |
| `tag_description` | string | Tag description |
| `event_type` | string | Alarm type (ALARM_HIGH_CRITICAL, etc.) |
| `action_type` | string | RAISED, ACKNOWLEDGED, CLEARED, etc. |
| `action_timestamp` | string | ISO 8601 timestamp |
| `performed_by` | string | Username/operator |
| `previous_state` | string | State before action |
| `new_state` | string | State after action |
| `alarm_priority` | int | Priority (1-5, 5=CRITICAL) |
| `priority_label` | string | CRITICAL, HIGH, MEDIUM, LOW, INFO |
| `alarm_actual_value` | float | Process value at time of action |
| `alarm_setpoint` | float | Alarm threshold |
| `action_reason` | string | Reason for action (clear reason) |
| `action_notes` | string | Operator notes |
| `session_id` | string | User session ID |
| `client_ip` | string | Operator IP address |
| `metadata` | object | Additional context (JSON) |
| `minutes_since_previous_action` | float | Time since previous action (minutes) |
| `response_time_seconds` | float | Response time in seconds |

### Action Types

- `RAISED` - Alarm was raised by the system
- `ACKNOWLEDGED` - Operator acknowledged the alarm
- `CLEARED` - Operator cleared the alarm
- `SUPPRESSED` - Alarm was suppressed (future)
- `UNSUPPRESSED` - Alarm suppression removed (future)
- `SHELVED` - Alarm was shelved (future)
- `UNSHELVED` - Alarm unshelved (future)

### Alarm States

- `ACTIVE` - Alarm is active and needs attention
- `ACKNOWLEDGED` - Operator has acknowledged
- `CLEARED` - Alarm has been resolved
- `SUPPRESSED` - Temporarily hidden (future)

---

## Python Client Example

```python
import requests

BASE_URL = "http://localhost:6001/api/alarms"

# Get audit trail for alarm
alarm_id = 12345
response = requests.get(f"{BASE_URL}/audit/{alarm_id}")
data = response.json()

if data['success']:
    print(f"Audit trail for alarm {alarm_id}:")
    for record in data['audit_trail']:
        print(f"  {record['action_timestamp']}: {record['action_type']} by {record['performed_by']}")
else:
    print(f"Error: {data['error']}")

# Get operator statistics
operator = "john_smith"
response = requests.get(f"{BASE_URL}/audit/operator/{operator}/stats", params={'days': 7})
data = response.json()

if data['success']:
    stats = data['stats']
    print(f"\nOperator {operator} statistics:")
    print(f"  Total actions: {stats['total_actions']}")
    print(f"  Acknowledgments: {stats['acks_count']}")
    print(f"  Average response time: {stats['avg_ack_response_minutes']:.2f} minutes")

# Get unacknowledged alarms
response = requests.get(f"{BASE_URL}/audit/unacknowledged", params={'hours': 24})
data = response.json()

if data['success']:
    print(f"\nUnacknowledged alarms: {data['count']}")
    for alarm in data['unacknowledged_alarms']:
        print(f"  {alarm['tag_name']}: {alarm['minutes_since_raised']:.1f} minutes")
```

---

## Testing with cURL

### Test all endpoints:

```bash
# 1. Get audit trail for alarm 12345
curl -s http://localhost:6001/api/alarms/audit/12345 | python -m json.tool

# 2. Get audit trail for tag
curl -s "http://localhost:6001/api/alarms/audit/tag/Pump_01_Pressure?limit=10" | python -m json.tool

# 3. Get operator statistics
curl -s "http://localhost:6001/api/alarms/audit/operator/operator/stats?days=7" | python -m json.tool

# 4. Get unacknowledged alarms
curl -s "http://localhost:6001/api/alarms/audit/unacknowledged?hours=24" | python -m json.tool
```

---

## Integration with Frontend

### React/TypeScript Example

```typescript
interface AuditRecord {
  audit_id: number;
  action_type: string;
  action_timestamp: string;
  performed_by: string;
  previous_state: string | null;
  new_state: string;
  action_notes?: string;
  response_time_seconds?: number;
}

async function getAlarmAuditTrail(alarmId: number): Promise<AuditRecord[]> {
  const response = await fetch(`/api/alarms/audit/${alarmId}`);
  const data = await response.json();
  
  if (data.success) {
    return data.audit_trail;
  } else {
    throw new Error(data.error);
  }
}

async function getOperatorStats(operator: string, days: number = 7) {
  const response = await fetch(
    `/api/alarms/audit/operator/${operator}/stats?days=${days}`
  );
  const data = await response.json();
  
  if (data.success) {
    return data.stats;
  } else {
    throw new Error(data.error);
  }
}
```

---

## Database Views

For direct database access, use the enhanced view:

```sql
-- Get audit trail with all enhancements
SELECT * FROM historian_raw.v_alarm_audit_trail
WHERE event_id = 12345
ORDER BY action_timestamp ASC;

-- Get operator performance
SELECT 
  performed_by,
  COUNT(*) as total_actions,
  AVG(minutes_since_previous_action) as avg_response_minutes
FROM historian_raw.v_alarm_audit_trail
WHERE action_type = 'ACKNOWLEDGED'
  AND action_timestamp >= NOW() - INTERVAL '7 days'
GROUP BY performed_by;
```

---

**Last Updated:** January 28, 2026  
**Version:** 1.0  
**Status:** Production Ready
