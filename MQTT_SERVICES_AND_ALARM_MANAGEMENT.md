# MQTT Services and Alarm Management Architecture

**Document Version:** 1.0  
**Last Updated:** May 28, 2026  
**Status:** Production Architecture Documentation

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [MQTT Services Overview](#mqtt-services-overview)
3. [Alarm Management Architecture](#alarm-management-architecture)
4. [Data Flow Diagrams](#data-flow-diagrams)
5. [Database Schema](#database-schema)
6. [API Endpoints](#api-endpoints)
7. [Configuration](#configuration)
8. [Operational Guidelines](#operational-guidelines)

---

## Executive Summary

This document describes the MQTT and alarm management architecture for the Cereveate HMI Production system. The system consists of multiple services that handle real-time data streaming, alarm evaluation, and operator interactions following ISA-18.2 standards.

### Key Components

| Component | Purpose | Status | Database Writes |
|-----------|---------|--------|----------------|
| **C# OPC Backend** | Primary OPC data writer & alarm authority | ✅ Active | `historian_timeseries`, `historian_events`, `alarm_active` |
| **HMI Flask (MQTT Client)** | Real-time WebSocket broadcast & audit trail | ✅ Active | `alarm_audit_trail` only |
| **mqtt_subscriber_service** | Independent MQTT→DB writer | ❌ Stopped | ~~`historian_timeseries`~~ (disabled) |

### Design Principles

- **Single Source of Truth**: C# AlarmStateManager is sole authority for alarm state
- **Separation of Concerns**: MQTT used for notifications only, REST API for commands
- **No Duplicate Writes**: Each service has distinct database responsibilities
- **ISA-18.2 Compliance**: 4-state alarm model with full audit trail

---

## MQTT Services Overview

### 1. C# OPC Backend MQTT Publisher

**Location:** `CSharpBackend/Services/OpcMqttPublisherService.cs`  
**Status:** ✅ Active  
**Purpose:** Publishes OPC/PLC tag values and alarm events to MQTT broker

#### Responsibilities

1. **Historian Data Publishing**
   - Polls OPC DA servers every 2 seconds
   - Writes to `historian_timeseries` (sample_source='OPC' or 'PLC')
   - Publishes same data to MQTT broker for real-time distribution
   - Uses bulk format: `{ values: [{ tag, value, quality, timestamp }] }`

2. **Alarm Event Publishing**
   - Subscribes to `AlarmStateManager.TransitionOccurred` events
   - Publishes alarm state changes to MQTT topics:
     - `alarms/raised` - New alarm (ACTIVE_UNACK)
     - `alarms/ack` - Alarm acknowledged (ACTIVE_ACK)
     - `alarms/rtn` - Alarm returned to normal (RTN_UNACK)
     - `alarms/cleared` - Alarm cleared (CLEARED)

#### MQTT Configuration

```json
{
  "OpcMqtt": {
    "BrokerHost": "127.0.0.1",
    "BrokerPort": 1883,
    "PublishMode": "Bulk",
    "MaxTagsPerBatch": 100,
    "PublishIntervalMs": 2000
  }
}
```

#### Data Flow

```
C# Backend → MQTT Publish
    ↓
[MQTT Broker:1883]
    ↓
Subscribers: HMI MQTT Client, mqtt_subscriber_service (if enabled)
```

#### Fallback Mechanism

**C# has built-in resilience:**
- Primary: BINARY COPY for batch inserts to PostgreSQL
- Fallback: Individual INSERT statements if COPY fails
- Metrics tracked: `_totalDbFailures`, `_totalFallbackInserts`
- **No external fallback service needed**

**File:** `PlcHistorianIngestService.cs`, Lines 400-460

```csharp
try {
    // BINARY COPY batch write (fast)
    await writer.WriteAsync("COPY historian_raw.historian_timeseries ...");
}
catch (Exception copyEx) {
    // FALLBACK: individual INSERT per record
    await FallbackInsertAsync(records, ct);
}
```

---

### 2. HMI MQTT Client Service

**Location:** `HMI/services/mqtt_client_service.py`  
**Status:** ✅ Active  
**Purpose:** Receives MQTT messages and broadcasts to WebSocket clients

#### Responsibilities

1. **Real-Time Data Broadcasting** (PRIMARY FUNCTION)
   - Subscribes to MQTT topics from broker
   - Filters tags based on user permissions (plant/area RBAC)
   - Broadcasts to browser via `socketio.emit('mqtt_tag_update', ...)`
   - **Does NOT write tag data to database** (disabled May 23, 2026)

2. **Alarm Action Audit Trail** (SECONDARY FUNCTION)
   - Writes operator actions to `alarm_audit_trail` table:
     - ACKNOWLEDGED - Operator ACK action
     - SUPPRESSED - Temporary alarm suppression
     - UNSUPPRESSED - Lifted suppression
     - CLEARED - Manual alarm clear
   - **Different from alarm state** (state managed by C#)

#### What Was Disabled

**File:** `HMI/app.py`, Line 1103

```python
# DISABLED 2026-05-23 — C# OPC/PLC historian now owns all writes to historian_timeseries.
# HMI was writing sample_source='MQTT' causing duplicate rows alongside C#'s OPC/PLC writes.
# Keep: alarm_audit_trail (alarm_controller.py), report_gen_log, tag_alarm_config — unaffected.
# _persist_mqtt_samples(filtered_tags, topic)
```

**Reason for Disabling:**
- Created duplicate rows in `historian_timeseries`
- Same OPC data written twice (C#: 'OPC', HMI: 'MQTT')
- C# backend is authoritative source for historian data

#### Current Behavior

**File:** `HMI/app.py`, `on_mqtt_message()` function

```python
def on_mqtt_message(topic, filtered_tags, raw_data):
    # ✅ DOES: Update in-memory cache
    for tag in filtered_tags:
        latest_tag_values[tag_id] = { value, quality, timestamp, source: 'MQTT' }
    
    # ✅ DOES: Broadcast to WebSocket per-user (RBAC filtered)
    socketio.emit('mqtt_tag_update', {
        'topic': topic, 
        'tags': user_filtered_tags
    }, room=sid)
    
    # ✅ DOES: Emit alarm notifications
    socketio.emit('mqtt_alarm', alarm_data)
    
    # ❌ DOES NOT: Write to historian_timeseries
    # _persist_mqtt_samples() is commented out
```

#### Alarm Audit Trail Writes

**File:** `HMI/controllers/alarm_controller.py`

```python
@alarm_bp.route('/acknowledge/<int:alarm_id>', methods=['POST'])
def acknowledge_alarm(alarm_id):
    # 1. Proxy to C# AlarmStateManager
    response = requests.post(
        f"{_OPC_BASE}/api/alarms/{encoded_key}/ack",
        json={'operator': username, 'notes': notes}
    )
    
    # 2. If C# succeeds, write audit trail
    if response.ok:
        cursor.execute("""
            INSERT INTO historian_raw.alarm_audit_trail
                (event_id, tag_id, action_type, performed_by, 
                 action_timestamp, action_notes, client_ip)
            VALUES (%s, %s, 'ACKNOWLEDGED', %s, NOW(), %s, %s)
        """, (alarm_id, tag_id, username, notes, request.remote_addr))
```

**Key Distinction:**
- `alarm_audit_trail` = WHO did WHAT, WHEN, WHY (compliance record)
- `historian_events` = WHAT happened to the alarm state (technical record)
- Different tables, different purposes, no duplication

---

### 3. mqtt_subscriber_service (DISABLED)

**Location:** `mqtt_subscriber_service/`  
**Status:** ❌ Not Running (Windows service not installed)  
**Last Activity:** May 25, 2026

#### What It Does (When Running)

1. **Subscribes to MQTT Broker**
   - Independent Python service
   - 20 worker threads for message processing
   - Validates tags against `tag_master` cache

2. **Writes to Database**
   - Table: `historian_raw.historian_timeseries`
   - Sample source: 'MQTT'
   - Rate limiting: Uses `db_logging_interval_ms` and `deadband_value` from tag_master
   - Deduplication: `ON CONFLICT (time, tag_id) DO UPDATE`

3. **Audit Trail**
   - Tracks all messages in `mqtt_audit_main` and `mqtt_audit_history`
   - Full lifecycle logging (received → validated → inserted)

#### Why It's Disabled

**Configuration:** `mqtt_subscriber_service/config/service_config.yaml`

```yaml
processing:
  enable_retries: false     # Fail-fast design
  validate_against_tag_master: true
  reject_unknown_tags: true
```

**Reasons:**
1. ❌ **Not a fallback mechanism** - No coordination with C# backend
2. ❌ **Creates duplicates** - Writes same OPC data C# already wrote
3. ❌ **Has bugs** - NULL tag_id constraint violations found in logs
4. ✅ **C# has internal fallback** - COPY → INSERT fallback already exists
5. ❌ **Fail-fast design** - Not designed for resilience/retry

**Evidence from Logs (May 25, 2026):**

```
ERROR: null value in column "tag_id" violates not-null constraint
Failing row: (2026-05-25 21:21:58..., null, 8297.8850709...)
```

#### When to Use This Service

- **Never for OPC/PLC data** (C# owns this)
- **Only if** you have MQTT-only data sources (not connected to C# OPC)
- **Only after** fixing NULL tag_id bugs
- **Only if** C# historian is completely disabled

---

## Alarm Management Architecture

### ISA-18.2 Four-State Model

The system implements ISA-18.2 alarm management with four distinct states:

```
NORMAL (no alarm)
    ↓ Tag crosses threshold
ACTIVE_UNACK (alarm active, operator has not acknowledged)
    ↓ Operator ACK
ACTIVE_ACK (alarm active, operator acknowledged)
    ↓ Tag returns to normal
RTN_UNACK (returned to normal, operator has not acknowledged return)
    ↓ Operator ACK
CLEARED (alarm fully resolved, row deleted)
```

### C# AlarmStateManager (Primary Authority)

**Location:** `CSharpBackend/Services/AlarmEvaluation/Services/AlarmStateManager.cs`

#### Design Principles

1. **Single Source of Truth**
   - Only C# writes to `historian_events` and `alarm_active`
   - In-memory state (`ConcurrentDictionary<string, AlarmRuntimeState>`)
   - Per-alarm-key locks (`SemaphoreSlim`) prevent race conditions

2. **Write-After-Success Pattern**
   - DB write happens first
   - Memory updated only after successful DB write
   - Invalid transitions rejected silently (logged at Warning)

3. **MQTT is Optional**
   - Failure to publish MQTT never affects alarm correctness
   - Fire-and-forget pattern via `TransitionOccurred` event

#### Responsibilities

**1. Raise Alarm (NORMAL → ACTIVE_UNACK)**

```csharp
public async Task<bool> RaiseAsync(
    string tagId, AlarmLevel level, double value, 
    double? setpointValue, int priority, DateTimeOffset timestamp)
{
    // 1. Check if already raised (avoid double-raise)
    if (_states.TryGetValue(alarmKey, out var existing))
        if (existing.State == AlarmState4.ActiveUnack)
            return false;
    
    // 2. Write to DB
    INSERT INTO historian_events (alarm_state='ACTIVE_UNACK')
    UPSERT alarm_active (current operational state)
    
    // 3. Update memory AFTER successful DB write
    _states[alarmKey] = new AlarmRuntimeState { ... };
    
    // 4. Emit event for MQTT publish
    EmitTransition(new AlarmTransitionEvent { ... });
    
    return true;
}
```

**2. Acknowledge Alarm (ACTIVE_UNACK → ACTIVE_ACK or RTN_UNACK → CLEARED)**

```csharp
public async Task<bool> AcknowledgeAsync(
    string alarmKey, string operatorName, string? notes)
{
    var state = _states[alarmKey];
    
    // Valid states: ACTIVE_UNACK, RTN_UNACK
    if (state.State not in [ActiveUnack, RtnUnack])
        return false;
    
    var isRtn = (state.State == AlarmState4.RtnUnack);
    var ackState = isRtn ? "CLEARED" : "ACTIVE_ACK";
    
    // Write to DB
    INSERT INTO historian_events (alarm_state=ackState)
    
    if (isRtn)
        DELETE FROM alarm_active WHERE alarm_key = @key
    else
        UPDATE alarm_active SET alarm_state='ACTIVE_ACK'
    
    // Update memory
    if (isRtn)
        _states.TryRemove(alarmKey, out _);
    else
        state.State = AlarmState4.ActiveAck;
    
    // Emit for MQTT
    EmitTransition(...);
    
    return true;
}
```

**3. Return to Normal (ACTIVE_UNACK/ACK → RTN_UNACK)**

Automatically triggered by `AlarmEvaluationService` when tag value returns below threshold.

**4. Clear Alarm (ACTIVE_ACK → CLEARED)**

```csharp
public async Task<bool> ClearAsync(
    string alarmKey, string operatorName, string? reason, 
    string? notes, bool forceAck = true)
{
    // forceAck: If still ACTIVE_UNACK, auto-ACK then clear atomically
    // Prevents race conditions
}
```

#### Circuit Breaker

**Purpose:** Suspend DB writes after consecutive failures

```csharp
private int _consecutiveDbFailures;
private DateTimeOffset _circuitOpenedAt;

private bool IsCircuitClosed()
{
    if (_consecutiveDbFailures < _alarmConfig.CircuitBreakerThreshold)
        return true;
    
    // Circuit open — wait for cooldown period
    if (DateTimeOffset.UtcNow - _circuitOpenedAt > _alarmConfig.CircuitBreakerCooldown)
    {
        ResetCircuitBreaker();
        return true;
    }
    
    return false;
}
```

#### Metrics

```csharp
private long _totalRaised;
private long _totalAcknowledged;
private long _totalRtn;
private long _totalCleared;

public (long raised, long ack, long rtn, long cleared) GetCounters()
    => (_totalRaised, _totalAcknowledged, _totalRtn, _totalCleared);
```

---

### HMI Alarm Controller (Proxy Layer)

**Location:** `HMI/controllers/alarm_controller.py`

#### Responsibilities

**1. Proxy ACK/CLEAR to C#**

```python
_OPC_BASE = 'http://localhost:5001'
_OPC_CONNECT_TIMEOUT = 3   # seconds
_OPC_READ_TIMEOUT = 5      # seconds

@alarm_bp.route('/acknowledge/<int:alarm_id>', methods=['POST'])
def acknowledge_alarm(alarm_id):
    # 1. Get alarm details from DB
    cursor.execute("SELECT alarm_key, tag_id FROM alarm_active WHERE current_event_id = %s", (alarm_id,))
    
    # 2. Proxy to C# AlarmStateManager
    response = requests.post(
        f"{_OPC_BASE}/api/alarms/{encoded_key}/ack",
        json={'operator': username, 'notes': notes},
        timeout=(_OPC_CONNECT_TIMEOUT, _OPC_READ_TIMEOUT)
    )
    
    if not response.ok:
        return jsonify({'success': False, 'error': 'C# ACK failed'}), 500
    
    # 3. Write audit trail (compliance record)
    cursor.execute("""
        INSERT INTO historian_raw.alarm_audit_trail
            (event_id, tag_id, action_type, performed_by, 
             previous_state, new_state, action_timestamp,
             action_notes, client_ip)
        VALUES (%s, %s, 'ACKNOWLEDGED', %s, %s, %s, NOW(), %s, %s)
    """, (alarm_id, tag_id, username, 'ACTIVE_UNACK', 'ACTIVE_ACK', notes, request.remote_addr))
    
    return jsonify({'success': True})
```

**2. Query Active Alarms**

```python
@alarm_bp.route('/active', methods=['GET'])
def get_active_alarms():
    # Read from alarm_active (C# writes, HMI reads)
    query = """
        SELECT alarm_key, tag_id, level, alarm_state, 
               raised_at, ack_at, ack_by, priority
        FROM historian_raw.alarm_active
        WHERE alarm_state IN ('ACTIVE_UNACK', 'ACTIVE_ACK', 'RTN_UNACK')
        ORDER BY raised_at DESC
    """
```

**3. Query Alarm History**

```python
@alarm_bp.route('/history', methods=['GET'])
def get_alarm_history():
    # Read from historian_events (immutable journal)
    query = """
        SELECT event_id, time, tag_id, event_type, 
               alarm_state, alarm_level, message
        FROM historian_raw.historian_events
        WHERE alarm_state IS NOT NULL
        ORDER BY time DESC
    """
```

**4. Query Audit Trail**

```python
@alarm_bp.route('/audit/<int:alarm_id>', methods=['GET'])
def get_alarm_audit(alarm_id):
    # Read from alarm_audit_trail (HMI writes, HMI reads)
    query = """
        SELECT action_type, performed_by, action_timestamp,
               previous_state, new_state, action_reason, action_notes
        FROM historian_raw.alarm_audit_trail
        WHERE event_id = %s
        ORDER BY action_timestamp
    """
```

---

### C# Alarm API Endpoints

**Base URL:** `http://localhost:5001/api/alarms`

#### GET /api/alarms/active

Returns all rows from `alarm_active` table (non-cleared alarms).

**Response:**
```json
{
  "count": 3,
  "alarms": [
    {
      "alarm_key": "TAG_001:High",
      "tag_id": "TAG_001",
      "level": "High",
      "alarm_state": "ACTIVE_UNACK",
      "current_event_id": 12345,
      "occurrence_id": "uuid",
      "raised_at": "2026-05-28T10:30:00Z",
      "raised_value": 95.5,
      "setpoint_value": 90.0,
      "priority": 3
    }
  ]
}
```

#### GET /api/alarms/history

Returns transition journal from `historian_events` table.

**Query Parameters:**
- `limit` (default: 200, max: 5000)
- `tagId` (optional filter)
- `fromDate`, `toDate` (optional date range)

**Response:**
```json
{
  "count": 150,
  "events": [
    {
      "event_id": 12345,
      "time": "2026-05-28T10:30:00Z",
      "tag_id": "TAG_001",
      "event_type": "ALARM_HIGH",
      "alarm_state": "ACTIVE_UNACK",
      "alarm_level": "High",
      "alarm_actual_value": 95.5,
      "alarm_setpoint": 90.0,
      "alarm_priority": 3,
      "message": "TAG_001 exceeded high limit"
    }
  ]
}
```

#### POST /api/alarms/{key}/ack

Acknowledges an alarm.

**Request Body:**
```json
{
  "operator": "john_doe",
  "notes": "Investigating root cause"
}
```

**Response:**
```json
{
  "success": true,
  "alarm_key": "TAG_001:High",
  "acknowledged_by": "john_doe",
  "event_type": "ALARM_ACKNOWLEDGED",
  "new_state": "ACTIVE_ACK"
}
```

**State Transitions:**
- `ACTIVE_UNACK` → `ACTIVE_ACK`
- `RTN_UNACK` → `CLEARED` (row deleted from alarm_active)

#### POST /api/alarms/{key}/clear

Manually clears an alarm (operator override).

**Request Body:**
```json
{
  "operator": "jane_smith",
  "reason": "Equipment shutdown for maintenance",
  "notes": "Coordinated with operations"
}
```

**Response:**
```json
{
  "success": true,
  "alarm_key": "TAG_001:High",
  "cleared_by": "jane_smith",
  "event_type": "ALARM_CLEARED",
  "new_state": "CLEARED"
}
```

**Valid States:**
- `ACTIVE_ACK` → `CLEARED` (normal path)
- `ACTIVE_UNACK` → `CLEARED` (if `forceAck=true`, auto-ACK then clear)

#### GET /api/alarms/health

Returns alarm engine status.

**Response:**
```json
{
  "status": "ok",
  "engine": "AlarmStateManager",
  "active_count": 5,
  "unack_count": 3,
  "timestamp": "2026-05-28T10:30:00Z"
}
```

---

## Data Flow Diagrams

### OPC Data Flow (Tag Values)

```
┌─────────────────────────────────────────────────────────┐
│ OPC DA Servers                                           │
│  (PLC1, PLC2, PLC3...)                                  │
└────────────────────┬────────────────────────────────────┘
                     │ OPC DA protocol
                     ↓
┌─────────────────────────────────────────────────────────┐
│ C# OPC Backend                                           │
│  PlcDataLoggingService (polls every 2s)                 │
│   ↓                                                      │
│  PlcHistorianIngestService                              │
│   ├─ COPY batch write (primary)                         │
│   └─ Individual INSERT (fallback)                       │
│   ↓                                                      │
│  PostgreSQL: historian_timeseries                       │
│   sample_source = 'OPC' or 'PLC'                        │
│   ↓                                                      │
│  OpcMqttPublisherService                                │
│   └─ Publishes to MQTT broker                           │
└────────────────────┬────────────────────────────────────┘
                     │ MQTT publish
                     ↓
              [MQTT Broker:1883]
                     │
                     ↓
┌─────────────────────────────────────────────────────────┐
│ HMI Flask Backend                                        │
│  mqtt_client_service.py                                 │
│   ├─ Receives MQTT messages                             │
│   ├─ Filters by user permissions (RBAC)                 │
│   └─ socketio.emit('mqtt_tag_update')                   │
│       ↓                                                  │
│      WebSocket                                           │
│       ↓                                                  │
│  React Frontend (Browser)                               │
│   └─ Real-time tag value display                        │
└─────────────────────────────────────────────────────────┘
```

**Key Points:**
- C# writes to DB (authoritative source)
- MQTT is notification-only (read-only for HMI)
- HMI does NOT write tag data to historian_timeseries
- Real-time updates via WebSocket to browser

---

### Alarm Event Flow

```
┌─────────────────────────────────────────────────────────┐
│ C# AlarmEvaluationService                                │
│  (polls tags every 2s, checks against setpoints)        │
│   ↓                                                      │
│  Tag crosses threshold?                                 │
│   ↓ YES                                                  │
│  AlarmStateManager.RaiseAsync()                         │
│   ├─ INSERT historian_events (journal)                  │
│   ├─ UPSERT alarm_active (current state)                │
│   ├─ Update in-memory state                             │
│   └─ Emit TransitionOccurred event                      │
│       ↓                                                  │
│  OnTransitionOccurred() → MQTT publish                  │
└────────────────────┬────────────────────────────────────┘
                     │ MQTT: alarms/raised
                     ↓
              [MQTT Broker:1883]
                     │
                     ↓
┌─────────────────────────────────────────────────────────┐
│ HMI Flask Backend                                        │
│  on_mqtt_message() receives alarm                       │
│   └─ socketio.emit('mqtt_alarm', alarm_data)            │
│       ↓                                                  │
│      WebSocket                                           │
│       ↓                                                  │
│  React Frontend (Browser)                               │
│   └─ Displays alarm notification                        │
│       ↓                                                  │
│   User clicks "Acknowledge" button                      │
│       ↓                                                  │
│   POST /api/alarms/acknowledge/{id}                     │
└────────────────────┬────────────────────────────────────┘
                     │ REST API proxy
                     ↓
┌─────────────────────────────────────────────────────────┐
│ HMI Flask Backend                                        │
│  alarm_controller.py                                    │
│   ├─ GET alarm details from alarm_active                │
│   ├─ POST http://localhost:5001/api/alarms/{key}/ack   │
│   │   ↓                                                  │
│   │  C# AlarmStateManager.AcknowledgeAsync()            │
│   │   ├─ INSERT historian_events ('ACTIVE_ACK')         │
│   │   ├─ UPDATE alarm_active                            │
│   │   ├─ Update in-memory state                         │
│   │   └─ Emit TransitionOccurred → MQTT publish         │
│   │       ↓                                              │
│   └─ If C# success: INSERT alarm_audit_trail            │
│       (WHO acknowledged, WHEN, WHY, notes)              │
└─────────────────────────────────────────────────────────┘
                     │ MQTT: alarms/ack
                     ↓
              [MQTT Broker:1883]
                     │
                     ↓
                [Back to Browser]
              Real-time state update
```

**Key Points:**
- C# is sole authority for alarm state
- HMI proxies ACK/CLEAR to C# via REST API
- HMI writes audit trail (compliance record)
- MQTT provides real-time notifications
- Commands go via REST API, not MQTT

---

### MQTT Topics Structure

```
Root: cereveate/
  │
  ├─ opc/
  │   ├─ values           (bulk tag updates from OPC servers)
  │   └─ status           (OPC server connection status)
  │
  ├─ plc/
  │   ├─ PLC1/values      (bulk tag updates from PLC1)
  │   ├─ PLC2/values      (bulk tag updates from PLC2)
  │   └─ PLC3/values      (bulk tag updates from PLC3)
  │
  └─ alarms/
      ├─ raised           (new alarms: ACTIVE_UNACK)
      ├─ ack              (acknowledged: ACTIVE_ACK)
      ├─ rtn              (returned to normal: RTN_UNACK)
      └─ cleared          (fully resolved: CLEARED)
```

**Payload Format (OPC/PLC):**

```json
{
  "gateway_id": "PLC1",
  "timestamp": "2026-05-28T10:30:00Z",
  "values": [
    {
      "tag": "TAG_001",
      "plcId": "PLC1",
      "value": 95.5,
      "quality": "Good",
      "timestamp": "2026-05-28T10:30:00.123Z",
      "dataType": "float"
    }
  ]
}
```

**Payload Format (Alarms):**

```json
{
  "alarm_key": "TAG_001:High",
  "occurrence_id": "uuid",
  "transition": "ACTIVE_UNACK",
  "event_type": "ALARM_HIGH",
  "new_state": "ACTIVE_UNACK",
  "tag_id": "TAG_001",
  "level": "High",
  "event_id": 12345,
  "transition_seq": 67890,
  "value": 95.5,
  "setpoint": 90.0,
  "operator": null,
  "timestamp": "2026-05-28T10:30:00Z"
}
```

---

## Database Schema

### historian_raw.historian_timeseries

**Purpose:** Time-series data storage for all tag values

```sql
CREATE TABLE historian_raw.historian_timeseries (
    time              TIMESTAMPTZ NOT NULL,
    tag_id            TEXT NOT NULL,
    value_num         DOUBLE PRECISION,
    value_text        TEXT,
    value_bool        BOOLEAN,
    quality           VARCHAR(10) DEFAULT 'G',
    sample_source     VARCHAR(20) DEFAULT 'UNKNOWN',  -- 'OPC', 'PLC', 'MQTT'
    mapping_version   INTEGER DEFAULT 1,
    opc_timestamp     TIMESTAMPTZ,
    
    PRIMARY KEY (time, tag_id)
);

-- TimescaleDB hypertable
SELECT create_hypertable('historian_raw.historian_timeseries', 'time');
```

**Sample Source Values:**
- `'OPC'` - Written by C# OpcMqttPublisherService
- `'PLC'` - Written by C# PlcHistorianIngestService
- `'MQTT'` - ~~Written by mqtt_subscriber_service~~ (disabled)

**Current Data Distribution:**

| sample_source | Active Writer | Status |
|---------------|---------------|--------|
| OPC | C# OpcMqttPublisherService | ✅ Active |
| PLC | C# PlcHistorianIngestService | ✅ Active |
| MQTT | mqtt_subscriber_service | ❌ Disabled |

---

### historian_raw.historian_events

**Purpose:** Immutable journal of all alarm state transitions (append-only)

```sql
CREATE TABLE historian_raw.historian_events (
    event_id              BIGSERIAL PRIMARY KEY,
    time                  TIMESTAMPTZ NOT NULL,
    tag_id                TEXT NOT NULL,
    event_type            VARCHAR(50) NOT NULL,
    severity              INTEGER,
    message               TEXT,
    alarm_state           VARCHAR(20),  -- 'ACTIVE_UNACK', 'ACTIVE_ACK', 'RTN_UNACK', 'CLEARED'
    alarm_priority        INTEGER,
    alarm_level           VARCHAR(20),  -- 'High', 'Low', 'HighHigh', 'LowLow'
    occurrence_id         UUID,
    instance_seq          INTEGER,
    transition_seq        BIGINT,       -- Global monotonic sequence
    alarm_actual_value    DOUBLE PRECISION,
    alarm_setpoint        DOUBLE PRECISION,
    
    CONSTRAINT historian_events_alarm_state_check 
        CHECK (alarm_state IS NULL OR alarm_state IN 
            ('ACTIVE_UNACK', 'ACTIVE_ACK', 'RTN_UNACK', 'CLEARED'))
);

CREATE INDEX idx_historian_events_alarm_state 
    ON historian_raw.historian_events(alarm_state, time DESC)
    WHERE alarm_state IS NOT NULL;
```

**Event Types:**
- `ALARM_HIGH`, `ALARM_LOW`, `ALARM_HIGHHIGH`, `ALARM_LOWLOW` - Alarm raised
- `ALARM_RTN` - Returned to normal
- `ALARM_ACK`, `ALARM_ACKNOWLEDGED` - Acknowledged
- `ALARM_CLEARED` - Cleared

**Written By:** C# AlarmStateManager ONLY  
**Never Delete:** Append-only journal for compliance

---

### historian_raw.alarm_active

**Purpose:** Current operational state of active alarms (runtime table)

```sql
CREATE TABLE historian_raw.alarm_active (
    alarm_key            TEXT PRIMARY KEY,  -- Composite: "TAG_001:High"
    tag_id               TEXT NOT NULL,
    level                VARCHAR(20) NOT NULL,
    alarm_state          VARCHAR(20) NOT NULL,
    current_event_id     BIGINT,
    occurrence_id        UUID NOT NULL,
    instance_seq         INTEGER NOT NULL,
    raised_at            TIMESTAMPTZ NOT NULL,
    raised_value         DOUBLE PRECISION,
    setpoint_value       DOUBLE PRECISION,
    ack_at               TIMESTAMPTZ,
    ack_by               TEXT,
    rtn_at               TIMESTAMPTZ,
    priority             INTEGER,
    transition_seq       BIGINT,
    updated_at           TIMESTAMPTZ DEFAULT NOW(),
    
    CONSTRAINT alarm_active_state_check 
        CHECK (alarm_state IN ('ACTIVE_UNACK', 'ACTIVE_ACK', 'RTN_UNACK'))
);

CREATE INDEX idx_alarm_active_state ON historian_raw.alarm_active(alarm_state);
CREATE INDEX idx_alarm_active_tag ON historian_raw.alarm_active(tag_id);
```

**Lifecycle:**
- INSERT when alarm raised (ACTIVE_UNACK)
- UPDATE when acknowledged (ACTIVE_ACK)
- UPDATE when returned to normal (RTN_UNACK)
- DELETE when cleared (CLEARED)

**Written By:** C# AlarmStateManager ONLY  
**Read By:** HMI Flask (via GET /api/alarms/active)

---

### historian_raw.alarm_audit_trail

**Purpose:** Operator action audit trail for compliance (WHO/WHEN/WHY)

```sql
CREATE TABLE historian_raw.alarm_audit_trail (
    audit_id             BIGSERIAL PRIMARY KEY,
    event_id             BIGINT NOT NULL,
    tag_id               TEXT NOT NULL,
    event_type           VARCHAR(20) DEFAULT 'ALARM',
    action_type          VARCHAR(50) NOT NULL,  -- 'ACKNOWLEDGED', 'CLEARED', 'SUPPRESSED', etc.
    action_timestamp     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    performed_by         TEXT NOT NULL,
    previous_state       VARCHAR(20),
    new_state            VARCHAR(20),
    alarm_priority       INTEGER,
    action_reason        TEXT,
    action_notes         TEXT,
    client_ip            TEXT,
    metadata             JSONB
);

CREATE INDEX idx_alarm_audit_event ON historian_raw.alarm_audit_trail(event_id);
CREATE INDEX idx_alarm_audit_action ON historian_raw.alarm_audit_trail(action_type, action_timestamp DESC);
```

**Action Types:**
- `ACKNOWLEDGED` - Operator acknowledged alarm
- `SUPPRESSED` - Temporarily suppressed alarm
- `UNSUPPRESSED` - Lifted suppression
- `CLEARED` - Manually cleared alarm

**Written By:** HMI Flask ONLY  
**Purpose:** Regulatory compliance (FDA 21 CFR Part 11, OSHA, ISA-18.2)

---

### historian_meta.tag_alarm_config

**Purpose:** Alarm setpoint configuration per tag and level

```sql
CREATE TABLE historian_meta.tag_alarm_config (
    config_id            SERIAL PRIMARY KEY,
    tag_id               TEXT NOT NULL,
    alarm_level          VARCHAR(20) NOT NULL,  -- 'High', 'Low', 'HighHigh', 'LowLow'
    setpoint_value       DOUBLE PRECISION NOT NULL,
    deadband_value       DOUBLE PRECISION DEFAULT 0.0,
    onset_delay_seconds  INTEGER DEFAULT 0,
    priority             INTEGER DEFAULT 2,
    enabled              BOOLEAN DEFAULT TRUE,
    
    UNIQUE(tag_id, alarm_level)
);
```

**Levels:**
- `HighHigh` - Critical high alarm (priority 3-4)
- `High` - Warning high alarm (priority 2)
- `Low` - Warning low alarm (priority 2)
- `LowLow` - Critical low alarm (priority 3-4)

**Read By:** C# AlarmSetpointCacheService (cached in memory)

---

## Configuration

### C# Backend (appsettings.json)

```json
{
  "HistorianConfig": {
    "Database": {
      "ConnectionString": "Host=localhost;Port=5432;Database=Automation_DB;Username=cereveate;Password=cereveate@222",
      "CommandTimeout": 30
    }
  },
  
  "AlarmEvaluation": {
    "Enabled": true,
    "EvaluationIntervalMs": 2000,
    "MqttClientIdSuffix": "alarm-eval",
    "MqttAlarmTopic": "alarms",
    "CircuitBreakerThreshold": 10,
    "CircuitBreakerCooldown": "00:05:00"
  },
  
  "OpcMqtt": {
    "Enabled": true,
    "BrokerHost": "127.0.0.1",
    "BrokerPort": 1883,
    "PublishMode": "Bulk",
    "MaxTagsPerBatch": 100,
    "PublishIntervalMs": 2000,
    "Username": "",
    "Password": ""
  },
  
  "PlcGateway": {
    "HistorianEnabled": true,
    "PollIntervalMs": 2000,
    "DefaultDbLoggingIntervalMs": 5000,
    "DefaultDeadband": 0.1,
    "MaxBatchSize": 1000
  }
}
```

### HMI Flask (config.json)

```json
{
  "database": {
    "host": "localhost",
    "port": 5432,
    "database": "Automation_DB",
    "user": "cereveate",
    "password": "cereveate@222"
  },
  
  "mqtt": {
    "broker_host": "127.0.0.1",
    "broker_port": 1883,
    "client_id": "hmi_mqtt_client",
    "keepalive": 60,
    "qos": 1,
    "topics": [
      "cereveate/opc/values",
      "cereveate/plc/+/values",
      "cereveate/alarms/#"
    ]
  },
  
  "websocket": {
    "enabled": true,
    "port": 8090,
    "ping_timeout": 60,
    "ping_interval": 25
  }
}
```

### mqtt_subscriber_service (service_config.yaml)

```yaml
service:
  name: MQTT_Subscriber_Service
  version: 1.0.0
  worker_threads: 20

mqtt:
  broker_host: localhost
  broker_port: 1883
  client_id: MqttSubscriber01
  qos: 1
  reconnect_on_failure: true

database:
  host: localhost
  port: 5432
  database: Automation_DB
  username: cereveate
  password: cereveate@222

processing:
  enable_retries: false            # Fail-fast design
  validate_against_tag_master: true
  reject_unknown_tags: true
  reject_disabled_tags: true
```

**Note:** This service is **NOT RUNNING** and should remain disabled.

---

## Operational Guidelines

### Service Startup Order

**Required Order:**

1. **PostgreSQL Database** (port 5432)
2. **MQTT Broker (Mosquitto)** (port 1883)
3. **C# Backend (OpcDaWebBrowser.exe)** (port 5001)
4. **HMI Flask Backend (app.py)** (port 8090)
5. **React Frontend** (npm run dev) (port 3000)

**Scripts:**
- `START_ALL.bat` - Starts all services in correct order
- `STOP_ALL.bat` - Stops all services gracefully

### Health Checks

**C# Backend:**
```bash
curl http://localhost:5001/api/alarms/health
```

Expected:
```json
{
  "status": "ok",
  "engine": "AlarmStateManager",
  "active_count": 5,
  "timestamp": "2026-05-28T10:30:00Z"
}
```

**HMI Flask:**
```bash
curl http://localhost:8090/api/health
```

**MQTT Broker:**
```bash
mosquitto_pub -t "test/ping" -m "hello" -h 127.0.0.1 -p 1883
```

### Monitoring

**Alarm Metrics (C#):**
```
GET /api/alarms/diagnostics
```

Returns:
- Total alarms raised
- Total acknowledged
- Total returned to normal
- Total cleared
- Circuit breaker status
- DB write failures

**Historian Metrics (C#):**
```
GET /api/plc/connections
```

Returns:
- Total DB writes
- Skipped (interval filter)
- Skipped (deadband filter)
- DB failures
- Fallback inserts count
- Last COPY duration

### Troubleshooting

**Problem:** Alarms not appearing in HMI

**Check:**
1. Is C# AlarmEvaluationService running?
   - `GET /api/alarms/health` should return 200 OK
2. Are alarm setpoints configured?
   - `SELECT * FROM historian_meta.tag_alarm_config WHERE enabled=true`
3. Is MQTT broker running?
   - `mosquitto_pub -t test -m hello`
4. Is HMI MQTT client connected?
   - Check HMI logs: `HMI/logs/hmi_app.log`
5. Check WebSocket connection in browser console

**Problem:** Duplicate data in historian_timeseries

**Check:**
1. Is mqtt_subscriber_service running?
   - Should be **STOPPED** - `sc query MQTTSubscriberService`
2. Is HMI `_persist_mqtt_samples()` commented out?
   - Should be **DISABLED** - check `HMI/app.py` line 1103

**Problem:** ACK/CLEAR not working

**Check:**
1. Is C# backend reachable?
   - `curl http://localhost:5001/api/alarms/health`
2. Check HMI logs for "C# ACK proxy connection refused"
3. Check alarm state - only ACTIVE_UNACK and RTN_UNACK can be ACK'd
4. Check permissions - does user have alarm acknowledgement rights?

### Log Locations

**C# Backend:**
- `CSharpBackend/bin/Release/net8.0/win-x86/publish/logs/`
- Look for: `AlarmStateManager`, `AlarmEvaluationService`

**HMI Flask:**
- `HMI/logs/hmi_app.log`
- `HMI/logs/hmi_errors.log`
- Look for: `[MQTT]`, `[ALARM_FLOW]`, `C# ACK proxy`

**mqtt_subscriber_service:**
- `mqtt_subscriber_service/logs/service.log`
- Should be empty (service not running)

### Database Maintenance

**Archive Old historian_events (older than 1 year):**

```sql
-- Move to archive table
INSERT INTO historian_raw.historian_events_archive
SELECT * FROM historian_raw.historian_events
WHERE time < NOW() - INTERVAL '1 year';

DELETE FROM historian_raw.historian_events
WHERE time < NOW() - INTERVAL '1 year';
```

**Clean alarm_audit_trail (older than 7 years for compliance):**

```sql
DELETE FROM historian_raw.alarm_audit_trail
WHERE action_timestamp < NOW() - INTERVAL '7 years';
```

**Vacuum TimescaleDB hypertables:**

```sql
SELECT compress_chunk(i)
FROM show_chunks('historian_raw.historian_timeseries', older_than => INTERVAL '7 days') i;
```

---

## Security Considerations

### Authentication

**C# Backend:**
- Currently allows anonymous access (`[AllowAnonymous]`)
- **TODO:** Implement JWT bearer token authentication

**HMI Flask:**
- JWT token-based authentication
- Tokens expire after 24 hours
- Refresh tokens supported

### Authorization

**Alarm Actions:**
- ACK requires `alarm_acknowledge` permission
- CLEAR requires `alarm_clear` permission
- SUPPRESS requires `alarm_suppress` permission

**RBAC Filtering:**
- Tag data filtered by plant/area permissions
- Users only see alarms for authorized areas

### Audit Trail

**Required Fields:**
- `performed_by` - username (cannot be null)
- `action_timestamp` - when action occurred
- `client_ip` - source IP address
- `action_reason` - why action was taken (for CLEAR/SUPPRESS)

**Compliance:**
- FDA 21 CFR Part 11 - Electronic signatures
- OSHA 1910.119 - Process Safety Management
- ISA-18.2 - Alarm Management

---

## Appendix A: MQTT Message Examples

### Tag Value Update (OPC)

```json
{
  "gateway_id": "OPC_SERVER_1",
  "timestamp": "2026-05-28T10:30:00.123Z",
  "values": [
    {
      "tag": "REACTOR_TEMP_001",
      "value": 185.5,
      "quality": "Good",
      "timestamp": "2026-05-28T10:30:00.123Z",
      "dataType": "float"
    },
    {
      "tag": "REACTOR_PRESSURE_001",
      "value": 15.2,
      "quality": "Good",
      "timestamp": "2026-05-28T10:30:00.123Z",
      "dataType": "float"
    }
  ]
}
```

### Tag Value Update (PLC)

```json
{
  "gateway_id": "PLC1",
  "timestamp": "2026-05-28T10:30:00.456Z",
  "values": [
    {
      "tag": "PLC1_AI_001",
      "plcId": "PLC1",
      "value": 72.3,
      "quality": "Good",
      "timestamp": "2026-05-28T10:30:00.456Z",
      "dataType": "float"
    }
  ]
}
```

### Alarm Raised

```json
{
  "alarm_key": "REACTOR_TEMP_001:High",
  "occurrence_id": "550e8400-e29b-41d4-a716-446655440000",
  "transition": "ACTIVE_UNACK",
  "event_type": "ALARM_HIGH",
  "new_state": "ACTIVE_UNACK",
  "tag_id": "REACTOR_TEMP_001",
  "level": "High",
  "event_id": 12345,
  "transition_seq": 67890,
  "value": 195.5,
  "setpoint": 190.0,
  "operator": null,
  "timestamp": "2026-05-28T10:30:05.000Z"
}
```

### Alarm Acknowledged

```json
{
  "alarm_key": "REACTOR_TEMP_001:High",
  "occurrence_id": "550e8400-e29b-41d4-a716-446655440000",
  "transition": "ACTIVE_ACK",
  "event_type": "ALARM_ACK",
  "new_state": "ACTIVE_ACK",
  "tag_id": "REACTOR_TEMP_001",
  "level": "High",
  "event_id": 12346,
  "transition_seq": 67891,
  "value": 195.5,
  "setpoint": 190.0,
  "operator": "john_doe",
  "timestamp": "2026-05-28T10:31:00.000Z"
}
```

### Alarm Cleared

```json
{
  "alarm_key": "REACTOR_TEMP_001:High",
  "occurrence_id": "550e8400-e29b-41d4-a716-446655440000",
  "transition": "CLEARED",
  "event_type": "ALARM_CLEARED",
  "new_state": "CLEARED",
  "tag_id": "REACTOR_TEMP_001",
  "level": "High",
  "event_id": 12347,
  "transition_seq": 67892,
  "value": 185.0,
  "setpoint": 190.0,
  "operator": "john_doe",
  "timestamp": "2026-05-28T10:35:00.000Z"
}
```

---

## Appendix B: State Transition Matrix

| Current State | Valid Actions | Next State | DB Operations |
|---------------|---------------|------------|---------------|
| NORMAL | Raise (tag crosses threshold) | ACTIVE_UNACK | INSERT historian_events, UPSERT alarm_active |
| ACTIVE_UNACK | Acknowledge | ACTIVE_ACK | INSERT historian_events, UPDATE alarm_active |
| ACTIVE_UNACK | Return to normal | RTN_UNACK | INSERT historian_events, UPDATE alarm_active |
| ACTIVE_UNACK | Clear (forceAck=true) | CLEARED | INSERT 2x historian_events, DELETE alarm_active |
| ACTIVE_ACK | Return to normal | RTN_UNACK | INSERT historian_events, UPDATE alarm_active |
| ACTIVE_ACK | Clear | CLEARED | INSERT historian_events, DELETE alarm_active |
| RTN_UNACK | Acknowledge | CLEARED | INSERT historian_events, DELETE alarm_active |
| RTN_UNACK | Re-trigger | ACTIVE_UNACK | INSERT historian_events, UPDATE alarm_active |

**Invalid Transitions (rejected silently):**
- ACTIVE_ACK → ACTIVE_UNACK (cannot un-acknowledge)
- CLEARED → any (alarm no longer exists)
- NORMAL → ACTIVE_ACK (must go through ACTIVE_UNACK first)

---

## Appendix C: Performance Metrics

### C# Backend

**Historian Write Performance:**
- BINARY COPY: ~5,000 records/second
- Individual INSERT fallback: ~500 records/second
- Target latency: < 10ms for batch write

**Alarm Evaluation:**
- Poll interval: 2 seconds
- Tags evaluated per cycle: ~1,000
- Typical evaluation time: < 100ms

### HMI Flask

**MQTT Message Processing:**
- Messages/second: ~100-200 (typical)
- WebSocket broadcast latency: < 50ms
- Concurrent connections: ~50 users

### MQTT Broker (Mosquitto)

**Capacity:**
- Messages/second: ~10,000
- Concurrent clients: ~1,000
- Typical CPU usage: < 5%

---

## Document Change Log

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-05-28 | System | Initial documentation |

---

## References

- ISA-18.2: Management of Alarm Systems for the Process Industries
- EEMUA 191: Alarm Systems - A Guide to Design, Management and Procurement
- FDA 21 CFR Part 11: Electronic Records; Electronic Signatures
- OSHA 1910.119: Process Safety Management of Highly Hazardous Chemicals

---

**END OF DOCUMENT**
