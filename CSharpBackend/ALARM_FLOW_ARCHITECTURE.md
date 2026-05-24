# Alarm Flow Architecture - Real-Time System

## Complete Alarm Data Flow (ISA-18.2 Compliant)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         ALARM GENERATION & FLOW                          │
└─────────────────────────────────────────────────────────────────────────┘

1. MQTT TEST PUBLISHER (test_mqtt_publisher_from_db.py)
   ├─ Reads tags from PostgreSQL (historian_meta.tag_master)
   ├─ Simulates realistic turbine sensor data
   ├─ Generates alarms when limits exceeded:
   │  • CRITICAL alarms (severity=1, priority=5)
   │  • WARNING alarms (severity=2, priority=2)
   ├─ Publishes to MQTT Broker (127.0.0.1:1883) with format:
   │  {
   │    "timestamp": "2026-01-27T14:22:16.372Z",
   │    "alarm_summary": {
   │      "alarms": [
   │        {
   │          "tag_id": "Pump_Discharge_Pressure",
   │          "event_type": "ALARM_LOW_CRITICAL",
   │          "severity": 1,
   │          "message": "Value 2.45 below CRITICAL LOW limit 6.0",
   │          "time": "2026-01-27T14:22:16.372Z",
   │          "metadata": {
   │            "alarm_value": 2.45,
   │            "setpoint": 6.0,
   │            "unit": "bar",
   │            "state": "ACTIVE"
   │          }
   │        }
   │      ]
   │    }
   │  }
   └─ ✅ Alarms ARE being generated in MQTT publisher

                    ↓ MQTT Protocol (port 1883)

2. MQTT SUBSCRIBER SERVICE (mqtt_subscriber_service/src/)
   ├─ Listens on MQTT Broker topics
   ├─ message_processor.py processes alarm_summary
   ├─ historian_dao.py writes to PostgreSQL with:
   │  
   │  🔹 ALARM DEDUPLICATION (ISA-18.2 Compliant):
   │     • Checks if ACTIVE alarm exists (tag_id + event_type)
   │     • IF EXISTS → UPDATE timestamp, value, message
   │     • IF NOT EXISTS → INSERT new alarm with alarm_state='ACTIVE'
   │     • Maps severity to priority: 1→5 (CRITICAL), 2→2 (WARNING)
   │     • Maps metadata: alarm_value→alarm_actual_value, setpoint→alarm_setpoint
   │
   └─ Writes to historian_raw.historian_events table:
      • alarm_state = 'ACTIVE'
      • alarm_priority = 5 (CRITICAL) or 2 (WARNING)
      • alarm_actual_value = current value
      • alarm_setpoint = threshold value

                    ↓ Database Insert

3. POSTGRESQL DATABASE (Historian_data)
   └─ historian_raw.historian_events table:
      ├─ Stores alarms with lifecycle states:
      │  • ACTIVE: New alarm, needs attention
      │  • ACKNOWLEDGED: Operator acknowledged, working on it
      │  • CLEARED: Issue resolved, alarm closed
      ├─ Columns:
      │  • event_id (PK)
      │  • tag_id
      │  • event_type (ALARM_LOW_CRITICAL, ALARM_HIGH_WARNING, etc.)
      │  • alarm_state ('ACTIVE', 'ACKNOWLEDGED', 'CLEARED')
      │  • alarm_priority (1-5, where 5=CRITICAL)
      │  • alarm_actual_value
      │  • alarm_setpoint
      │  • acknowledged_by, acknowledged_at
      │  • cleared_at
      │  • time (raised_at)
      └─ Deduplication: Only ONE ACTIVE alarm per tag+event_type

                    ↓ Two Parallel Paths

┌─────────────────────────────────┐  ┌─────────────────────────────────┐
│   PATH A: REAL-TIME UPDATES     │  │   PATH B: REST API POLLING      │
└─────────────────────────────────┘  └─────────────────────────────────┘

4A. BACKEND SOCKETIO (app.py)          4B. BACKEND REST API (alarm_controller.py)
   ├─ MQTT callback receives data         ├─ GET /api/alarms/active?limit=10
   ├─ Emits 'mqtt_alarm' event via        ├─ Queries database:
   │  SocketIO to all clients             │  SELECT * FROM historian_events
   └─ Real-time push (<1 second)          │  WHERE alarm_state IN ('ACTIVE', 'ACKNOWLEDGED')
                                          │  ORDER BY alarm_priority DESC
                    ↓                     └─ Polling interval: 30 seconds (backup)
                                          
                                                     ↓

5. FRONTEND ALARM PANEL (AlarmPanel.tsx)
   ├─ DUAL UPDATE MECHANISM:
   │  
   │  🔹 PRIMARY: Real-Time WebSocket Updates
   │     • Listens to 'mqtt_alarm' SocketIO events
   │     • Instant alarm display (<1 second latency)
   │     • Automatic deduplication by tag_id + event_type
   │     • Updates existing alarms, adds new ones
   │
   │  🔹 BACKUP: REST API Polling
   │     • Fetches from /api/alarms/active every 30 seconds
   │     • Ensures consistency with database
   │     • Recovers from missed WebSocket events
   │
   ├─ Display Features:
   │  • Sorted by priority (CRITICAL first)
   │  • Color-coded per EEMUA 191: RED (Critical), YELLOW (Warning)
   │  • Shows: Tag, Message, Value, Setpoint, Duration
   │  • ISA-18.2 lifecycle buttons: ACK, CLEAR
   │
   └─ Operator Actions:
      • ACKNOWLEDGE: alarm_state → 'ACKNOWLEDGED'
      • CLEAR: Opens dialog with mandatory reason (10 options)
               alarm_state → 'CLEARED' (removed from panel)

```

## Key Features Implemented

### ✅ Alarm Generation (MQTT Publisher)
- ✅ Realistic alarms based on tag limits
- ✅ Millisecond-precision timestamps
- ✅ Metadata includes value, setpoint, unit, equipment info
- ✅ Published every 1 second

### ✅ Alarm Deduplication (MQTT Subscriber)
- ✅ Prevents duplicate ACTIVE alarms (ISA-18.2)
- ✅ Updates existing alarm timestamp/value
- ✅ Only creates new entry when state changes
- ✅ Proper priority mapping (1=CRITICAL→5, 2=WARNING→2)

### ✅ Alarm Storage (PostgreSQL)
- ✅ Full lifecycle tracking (ACTIVE → ACKNOWLEDGED → CLEARED)
- ✅ Audit trail: timestamps, user, clear reasons
- ✅ Query optimization: Only ACTIVE/ACKNOWLEDGED shown

### ✅ Real-Time Updates (WebSocket/SocketIO)
- ✅ Instant alarm push to all connected clients
- ✅ <1 second latency from sensor to HMI
- ✅ Automatic reconnection handling
- ✅ Bi-directional communication

### ✅ Alarm Panel Display (Frontend)
- ✅ Real-time updates via WebSocket + REST backup
- ✅ ISA-18.2 compliant lifecycle (ACK → CLEAR)
- ✅ Mandatory clear documentation (10 reasons)
- ✅ EEMUA 191 color coding
- ✅ Priority-based sorting
- ✅ Auto-refresh every 30 seconds (backup)

## Alarm Lifecycle Example

```
Time 10:00:00 - Pump_Discharge_Pressure drops to 2.45 bar (limit: 6.0 bar)
            ↓
Time 10:00:01 - MQTT Publisher generates ALARM_LOW_CRITICAL
            ↓
Time 10:00:01 - MQTT Subscriber inserts: alarm_state='ACTIVE', priority=5
            ↓
Time 10:00:01 - Backend emits 'mqtt_alarm' via SocketIO
            ↓
Time 10:00:02 - Frontend displays RED alarm in AlarmPanel
            ↓
Time 10:00:05 - Pump still low, MQTT sends another alarm
            ↓
Time 10:00:05 - MQTT Subscriber UPDATES existing alarm (no duplicate!)
            ↓
Time 10:03:00 - Operator clicks ACK button
            ↓
Time 10:03:00 - Backend: alarm_state='ACKNOWLEDGED', acknowledged_by='shakil'
            ↓
Time 10:03:00 - AlarmPanel shows green checkmark, acknowledger name
            ↓
Time 10:05:00 - Operator fixes pump, clicks CLEAR button
            ↓
Time 10:05:00 - Frontend shows dialog with 10 clear reasons
            ↓
Time 10:05:10 - Operator selects "Equipment repaired/restarted" + notes
            ↓
Time 10:05:10 - Backend: alarm_state='CLEARED', cleared_at=NOW()
            ↓
Time 10:05:10 - AlarmPanel removes alarm from display
            ↓
Time 10:05:11 - Database query excludes CLEARED alarms
            ↓
✅ Alarm lifecycle complete!
```

## Configuration

### MQTT Broker
- Host: `127.0.0.1`
- Port: `1883`
- Protocol: MQTT v3.1.1

### Backend API
- Flask: `http://localhost:6001`
- SocketIO: `ws://localhost:6001`

### Database
- PostgreSQL: `localhost:5432`
- Database: `Historian_data`
- Schema: `historian_raw.historian_events`

### Update Intervals
- MQTT Publish: 1 second
- Real-time Push: <1 second (instant)
- REST Polling: 30 seconds (backup)

## Standards Compliance

✅ **ISA-18.2**: Alarm Management Lifecycle
- Single alarm instance per condition
- Proper state transitions
- Audit trail required
- Clear documentation mandatory

✅ **EEMUA 191**: Alarm System Design
- Priority-based color coding
- RED = Critical (Priority 5)
- YELLOW = Warning (Priority 2)

✅ **ISA-101**: HMI Design Guidelines
- Clear visual hierarchy
- Operator-focused interface
- Minimal clicks for critical actions

✅ **NAMUR NE 107**: Alarm Management Philosophy
- Alarm deduplication
- Prioritization
- Operator workload reduction
