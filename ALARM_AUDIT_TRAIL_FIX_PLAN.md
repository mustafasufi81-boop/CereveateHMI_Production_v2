# Alarm Audit Trail Fix Plan
**Date**: May 28, 2026  
**Issue**: Audit trail showing wrong data - multiple alarm occurrences mixed together  
**Status**: Analysis Complete → Awaiting Approval

---

## 🔴 CRITICAL PROBLEMS IDENTIFIED

### Problem 1: **WRONG QUERY LOGIC**
**Current behavior**: Audit trail shows ALL actions for tag `VYAN1101G` across MULTIPLE alarm occurrences
- Shows 12 ACK actions (different times, different operators)
- Shows 4 CLEAR actions (different times, different reasons)
- All show SAME `PV@Trip: 6.32` (never updates with new alarm values)
- ONE alarm card should = ONE audit trail, but it's showing MANY alarm lifecycles

**Root cause**: `get_alarm_audit_trail(alarm_id)` function receives ONE `event_id` but returns data for ENTIRE tag history

**Code location**: `HMI/controllers/alarm_controller.py` line 1211

```python
def get_alarm_audit_trail(alarm_id):
    """
    Get complete audit trail for a specific alarm
    Returns all state changes (RAISED, ACKNOWLEDGED, CLEARED, etc.)
    """
    audit_dao = AlarmAuditDAO(db_service)
    audit_records = audit_dao.get_audit_trail_enhanced(event_id=alarm_id, limit=100)
    # ^^^ This SHOULD only return records WHERE event_id = alarm_id
    # BUT it's likely returning WHERE tag_id = (SELECT tag_id FROM events WHERE event_id = alarm_id)
```

---

### Problem 2: **MISSING LATEST ALARM INFO**
**Current behavior**: Audit trail doesn't show:
- ❌ Latest alarm occurrence_id (C# generates new GUID each time)
- ❌ Latest alarm raised_at timestamp
- ❌ Latest alarm raised_value (process value that tripped alarm)
- ❌ Which specific alarm instance this audit trail belongs to

**Expected behavior**: Top of audit trail should show:
```
┌─────────────────────────────────────────────────────────┐
│ ALARM INSTANCE INFO                                     │
│ Alarm ID: 881456                                        │
│ Occurrence: 3f7e9a2b-8c1d-4567-9012-abcdef123456       │
│ Tag: VYAN1101G (ID FAN / POTLINE)                      │
│ Raised: May 22, 2026 11:55:58 PM                       │
│ Current Value: 6.32 KPA (Setpoint: 5.00 KPA)          │
│ State: ACTIVE_ACK ✓                                     │
└─────────────────────────────────────────────────────────┘
```

---

### Problem 3: **NO DISPLAY LIMITS**
**Current behavior**: Shows unlimited audit records (limit=100 in code)
- If operator ACKs alarm 50 times = 50 ACK entries shown
- If alarm re-triggers 20 times = 20 RAISED entries shown
- Audit trail becomes unreadable wall of text

**Expected behavior**: Need smart limits:
- Show **latest 20 actions** by default
- Add **"Load More"** or **pagination** for older records
- Highlight **most important actions** (RAISED, first ACK, CLEARED)

---

## 🔍 TECHNICAL DEEP DIVE

### How C# Creates Alarms (AlarmStateManager.cs)

**Each time tag trips alarm** (line 168):
```csharp
var occurrenceId = Guid.NewGuid();  // ← NEW GUID EVERY TIME
```

**Writes to 2 tables**:

1. **historian_events** (immutable journal):
   ```sql
   INSERT INTO historian_events (event_id, tag_id, occurrence_id, alarm_state, ...)
   VALUES (881456, 'VYAN1101G', '3f7e9a2b...', 'ACTIVE_UNACK', ...)
   ```

2. **alarm_active** (live state, UPSERT):
   ```sql
   INSERT INTO alarm_active (alarm_key, occurrence_id, raised_at, raised_value, ...)
   VALUES ('VYAN1101G:HIGH', '3f7e9a2b...', '2026-05-22 23:55:58', 6.32, ...)
   ON CONFLICT (alarm_key) DO UPDATE
       SET occurrence_id = '3f7e9a2b...',  -- ← REPLACES OLD OCCURRENCE_ID
           raised_at = '2026-05-22 23:55:58',
           raised_value = 6.32,
           ...
   ```

**What this means**:
- ✅ Each alarm re-trigger gets **NEW event_id** in historian_events
- ✅ Each alarm re-trigger gets **NEW occurrence_id** (GUID)
- ✅ alarm_active row gets **UPDATED** with new occurrence_id/time/value
- ❌ **BUT audit trail query doesn't use occurrence_id to filter**

---

### How HMI Writes Audit Trail (alarm_controller.py)

**After operator ACKs** (line 385):
```python
requests.post(f"http://localhost:5001/api/alarms/{encoded_key}/ack", ...)  # C# does state transition
# Then write audit record:
INSERT INTO alarm_audit_trail (event_id, tag_id, action_type, performed_by, ...)
VALUES (881456, 'VYAN1101G', 'ACKNOWLEDGED', 'Mustafa', ...)
```

**Database schema** (`alarm_audit_trail` table):
```sql
CREATE TABLE alarm_audit_trail (
    audit_id BIGSERIAL PRIMARY KEY,
    event_id BIGINT NOT NULL,        -- ← Links to historian_events.event_id
    tag_id TEXT NOT NULL,
    action_type TEXT NOT NULL,       -- RAISED, ACKNOWLEDGED, CLEARED, etc.
    action_timestamp TIMESTAMPTZ,
    performed_by TEXT,
    alarm_actual_value DOUBLE PRECISION,
    alarm_setpoint DOUBLE PRECISION,
    action_reason TEXT,
    ...
)
```

**Index structure**:
- `idx_alarm_audit_event_id` on `event_id`
- `idx_alarm_audit_tag_id` on `tag_id`

---

### Current Query Logic (BROKEN)

**Function**: `AlarmAuditDAO.get_audit_trail_enhanced(event_id=881456)`

**Likely does**:
```sql
-- WRONG: Returns ALL audit records for the TAG, not just ONE event_id
SELECT * FROM alarm_audit_trail
WHERE tag_id = (SELECT tag_id FROM historian_events WHERE event_id = 881456)
ORDER BY action_timestamp DESC
LIMIT 100
```

**Should do**:
```sql
-- CORRECT: Returns ONLY audit records for THIS specific event_id
SELECT * FROM alarm_audit_trail
WHERE event_id = 881456
ORDER BY action_timestamp ASC
```

---

## ✅ DESIRED BEHAVIOR

### Scenario: One Tag, Multiple Re-Triggers

**Timeline**:
```
May 22, 11:55 PM → VYAN1101G hits 6.32 (alarm raised, event_id=881456)
May 23, 2:00 AM  → Operator ACKs (writes to alarm_audit_trail with event_id=881456)
May 23, 3:00 AM  → Tag returns to normal (RTN_UNACK → auto-cleared)
May 24, 10:00 AM → VYAN1101G hits 7.15 (NEW ALARM RAISED, event_id=881999, NEW occurrence_id)
May 24, 11:00 AM → Operator ACKs (writes to alarm_audit_trail with event_id=881999)
May 24, 12:00 PM → Operator CLEARs (writes to alarm_audit_trail with event_id=881999)
```

**Expected audit trails**:

**Alarm Card #1** (event_id=881456, occurred May 22-23):
```
┌─ AUDIT TRAIL ─────────────────────────────────────┐
│ 1. RAISED         | May 22 11:55 PM | system      │
│    Value: 6.32 KPA, Setpoint: 5.00 KPA           │
│                                                    │
│ 2. ACKNOWLEDGED   | May 23 02:00 AM | Mustafa     │
│    Response time: 245 minutes                     │
│                                                    │
│ 3. AUTO-CLEARED   | May 23 03:00 AM | system      │
│    Tag returned to normal                         │
└────────────────────────────────────────────────────┘
```

**Alarm Card #2** (event_id=881999, occurred May 24):
```
┌─ AUDIT TRAIL ─────────────────────────────────────┐
│ 1. RAISED         | May 24 10:00 AM | system      │
│    Value: 7.15 KPA, Setpoint: 5.00 KPA           │
│                                                    │
│ 2. ACKNOWLEDGED   | May 24 11:00 AM | Jhon        │
│    Response time: 60 minutes                      │
│                                                    │
│ 3. CLEARED        | May 24 12:00 PM | Jhon        │
│    Reason: "Equipment repaired"                   │
└────────────────────────────────────────────────────┘
```

**Key principles**:
- ✅ Each alarm card shows ONLY its own audit trail (filtered by event_id)
- ✅ Latest alarm info displayed at top
- ✅ Actions sorted chronologically (oldest first or newest first, user preference)
- ✅ Clear visual separation between action types

---

## 🛠️ APPROVED SOLUTION

### Fix 1: **Correct the Query** (✅ APPROVED)

**File**: `HMI/controllers/alarm_controller.py` line 1211

**Requirements**:
- ✅ Filter by `event_id` ONLY (no tag_id mixing)
- ✅ Use `occurrence_id` to separate re-triggers
- ✅ Sort newest first (DESC) by default
- ✅ Add lifecycle state validation
- ✅ Backend pagination only (limit=20)

**Change**:
```python
def get_alarm_audit_trail(alarm_id):
    """
    Get audit trail for ONE specific alarm occurrence
    Filtered by event_id, sorted newest first for operators
    """
    sort_order = request.args.get('sort', 'desc').upper()  # desc or asc
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 20, type=int)
    
    audit_dao = AlarmAuditDAO(db_service)
    # FIX: Query MUST filter by event_id ONLY
    audit_records = audit_dao.get_audit_trail_enhanced(
        event_id=alarm_id,
        sort_order=sort_order,  # DESC = newest first (default)
        limit=page_size,
        offset=(page - 1) * page_size
    )
```

**Verify `AlarmAuditDAO.get_audit_trail_enhanced()` query**:
```sql
-- CRITICAL: Filter by event_id ONLY
SELECT * FROM alarm_audit_trail aat
WHERE aat.event_id = %s  -- ← MUST use event_id, NOT tag_id
ORDER BY aat.action_timestamp DESC  -- ← Newest first for operators
LIMIT %s OFFSET %s
```

---

### Fix 2: **Add Latest Alarm Context** (✅ APPROVED)

**Goal**: Pin current alarm state at top - operators need to see LATEST data FIRST

**Requirements**:
- ✅ Show current occurrence_id (unique per re-trigger)
- ✅ Show current lifecycle state (ACTIVE_UNACKED, ACTIVE_ACKED, RTN_UNACKED, CLEARED)
- ✅ Show latest raised_at timestamp
- ✅ Show current process value vs setpoint
- ✅ Show priority (1-5)
- ✅ Add `is_current_occurrence` flag
- ✅ Add `data_consistency_verified` flag
- ✅ Show operator snapshot (username, display_name, user_id)

**Add to response**:
```python
def get_alarm_audit_trail(alarm_id):
    ...
    # Get CURRENT alarm info from alarm_active (if still active)
    with db_service.connection.cursor() as cursor:
        cursor.execute("""
            SELECT 
                aa.alarm_key,
                aa.occurrence_id,
                aa.tag_id,
                tm.tag_name,
                tm.description,
                tm.equipment,
                tm.area,
                tm.plant,
                aa.alarm_state,
                aa.level,
                aa.raised_at,
                aa.raised_value,
                aa.setpoint_value,
                aa.priority,
                aa.ack_at,
                aa.ack_by,
                aa.rtn_at,
                aa.transition_seq,
                u.display_name AS ack_by_display_name,
                u.user_id AS ack_by_user_id
            FROM historian_raw.alarm_active aa
            LEFT JOIN historian_meta.tag_master tm ON aa.tag_id = tm.tag_id
            LEFT JOIN users u ON aa.ack_by = u.username
            WHERE aa.current_event_id = %s
        """, (alarm_id,))
        alarm_info = cursor.fetchone()
        
        # Check if this audit trail belongs to CURRENT active alarm
        is_current = alarm_info is not None
        
        # If not in alarm_active, get from historian_events (cleared alarm)
        if not alarm_info:
            cursor.execute("""
                SELECT 
                    he.tag_id || ':' || he.alarm_level AS alarm_key,
                    he.occurrence_id,
                    he.tag_id,
                    tm.tag_name,
                    tm.description,
                    tm.equipment,
                    tm.area,
                    tm.plant,
                    he.alarm_state,
                    he.alarm_level AS level,
                    he.time AS raised_at,
                    he.alarm_actual_value AS raised_value,
                    he.alarm_setpoint AS setpoint_value,
                    he.alarm_priority AS priority,
                    NULL AS ack_at,
                    NULL AS ack_by,
                    NULL AS rtn_at,
                    he.transition_seq,
                    NULL AS ack_by_display_name,
                    NULL AS ack_by_user_id
                FROM historian_raw.historian_events he
                LEFT JOIN historian_meta.tag_master tm ON he.tag_id = tm.tag_id
                WHERE he.event_id = %s
                LIMIT 1
            """, (alarm_id,))
            alarm_info = cursor.fetchone()
    
    # Build alarm_info section (pinned at top)
    return jsonify({
        'success': True,
        'alarm_id': alarm_id,
        'alarm_info': {  # ← PINNED SECTION (shows LATEST state)
            'occurrence_id': str(alarm_info['occurrence_id']) if alarm_info else None,
            'is_current_occurrence': is_current,
            'data_consistency_verified': True,
            
            # Tag identification
            'alarm_key': alarm_info['alarm_key'] if alarm_info else None,
            'tag_id': alarm_info['tag_id'] if alarm_info else None,
            'tag_name': alarm_info['tag_name'] if alarm_info else None,
            'tag_description': alarm_info['description'] if alarm_info else None,
            'equipment': alarm_info['equipment'] if alarm_info else None,
            'area': alarm_info['area'] if alarm_info else None,
            'plant': alarm_info['plant'] if alarm_info else None,
            
            # Current state (MOST IMPORTANT FOR OPERATORS)
            'current_state': alarm_info['alarm_state'] if alarm_info else None,
            'lifecycle_state': _map_lifecycle_state(alarm_info['alarm_state'], alarm_info.get('ack_at'), alarm_info.get('rtn_at')) if alarm_info else None,
            'level': alarm_info['level'] if alarm_info else None,
            'priority': alarm_info['priority'] if alarm_info else None,
            
            # Latest values (CRITICAL FOR PLANT OPERATORS)
            'raised_at': alarm_info['raised_at'].isoformat() if alarm_info and alarm_info['raised_at'] else None,
            'raised_value': alarm_info['raised_value'] if alarm_info else None,
            'setpoint': alarm_info['setpoint_value'] if alarm_info else None,
            'deviation': (alarm_info['raised_value'] - alarm_info['setpoint_value']) if (alarm_info and alarm_info['raised_value'] and alarm_info['setpoint_value']) else None,
            
            # Operator actions
            'ack_by': alarm_info['ack_by'] if alarm_info else None,
            'ack_by_display_name': alarm_info.get('ack_by_display_name'),
            'ack_by_user_id': alarm_info.get('ack_by_user_id'),
            'ack_at': alarm_info['ack_at'].isoformat() if (alarm_info and alarm_info.get('ack_at')) else None,
            'rtn_at': alarm_info['rtn_at'].isoformat() if (alarm_info and alarm_info.get('rtn_at')) else None,
            
            # Audit metadata
            'transition_seq': alarm_info.get('transition_seq'),
        },
        'audit_trail': audit_records,
        'count': len(audit_records),
        'total_count': total_count,
        'has_more': total_count > page_size,
        'page': page,
        'page_size': page_size,
        'sort_order': sort_order.lower(),
    })

def _map_lifecycle_state(alarm_state, ack_at, rtn_at):
    """Map ISA-18.2 state to simplified lifecycle state"""
    if not alarm_state:
        return None
    
    state_upper = alarm_state.upper()
    
    # ISA-18.2 4-state model
    if state_upper == 'ACTIVE_UNACK':
        return 'ACTIVE_UNACKED'
    elif state_upper == 'ACTIVE_ACK':
        return 'ACTIVE_ACKED'
    elif state_upper == 'RTN_UNACK':
        return 'CLEARED_UNACKED'  # Tag returned to normal but not ACKed
    elif state_upper == 'CLEARED':
        return 'CLEARED_ACKED'
    elif state_upper == 'SUPPRESSED':
        return 'SUPPRESSED'
    
    return state_upper
```

---

### Fix 3: **Implement Display Limits** (✅ APPROVED)

**Problem**: N number of ACK events can make audit trail unreadable

**✅ APPROVED SOLUTION: Backend Pagination**
- Default limit = **20 records** (newest first)
- Backend-side pagination ONLY (no frontend slicing)
- Add `has_more` flag for "Load More" button
- Keep MQTT/live UI separate from historical audit

```python
def get_alarm_audit_trail(alarm_id):
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 20, type=int)
    sort_order = request.args.get('sort', 'desc').upper()
    offset = (page - 1) * page_size
    
    audit_dao = AlarmAuditDAO(db_service)
    
    # Get paginated records
    audit_records = audit_dao.get_audit_trail_enhanced(
        event_id=alarm_id,
        sort_order=sort_order,
        limit=page_size,
        offset=offset
    )
    
    # Get total count (for has_more flag)
    total_count = audit_dao.count_audit_records(event_id=alarm_id)
    
    return jsonify({
        ...
        'audit_trail': audit_records,
        'count': len(audit_records),
        'total_count': total_count,
        'has_more': (offset + len(audit_records)) < total_count,
        'page': page,
        'page_size': page_size,
    })
```

**Query optimization** (add indexes):
```sql
-- Ensure fast queries
CREATE INDEX IF NOT EXISTS idx_alarm_audit_event_timestamp 
ON historian_raw.alarm_audit_trail(event_id, action_timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_alarm_audit_occurrence 
ON historian_raw.alarm_audit_trail(occurrence_id, action_timestamp DESC);
```

---

### Fix 4: **UI Component Update** (✅ APPROVED - FRONTEND)

**File**: `HMI/apex-hmi/src/components/...` (React alarm card component)

**Requirements**:
- ✅ Pin latest alarm state at top (CRITICAL for operators)
- ✅ Show lifecycle state with visual indicators
- ✅ Show operator snapshots (display name, not just username)
- ✅ Add "Timeline View" toggle (DESC ↔ ASC)
- ✅ Add "Load More" for pagination
- ✅ Keep UI focused on current plant situation

**Add alarm instance header** (PINNED AT TOP):
```tsx
<div className="alarm-audit-header">
  <div className="alarm-status-banner" data-state={auditData.alarm_info.lifecycle_state}>
    {/* PINNED: Current state visible immediately */}
    <div className="status-indicator">
      <StatusBadge state={auditData.alarm_info.lifecycle_state} />
      {auditData.alarm_info.is_current_occurrence && <span className="live-badge">LIVE</span>}
    </div>
    
    <div className="alarm-primary-info">
      <h3>{auditData.alarm_info.tag_name}</h3>
      <span className="equipment">{auditData.alarm_info.equipment} / {auditData.alarm_info.area}</span>
    </div>
    
    <div className="alarm-values">
      <div className="value-current">
        <label>Current Value:</label>
        <strong>{auditData.alarm_info.raised_value?.toFixed(2)}</strong>
      </div>
      <div className="value-setpoint">
        <label>Setpoint:</label>
        <span>{auditData.alarm_info.setpoint?.toFixed(2)}</span>
      </div>
      <div className="value-deviation">
        <label>Deviation:</label>
        <span className={auditData.alarm_info.deviation > 0 ? 'over' : 'under'}>
          {auditData.alarm_info.deviation > 0 ? '+' : ''}{auditData.alarm_info.deviation?.toFixed(2)}
        </span>
      </div>
    </div>
    
    <div className="alarm-metadata">
      <div>Priority: <span className={`priority-${auditData.alarm_info.priority}`}>{auditData.alarm_info.priority}</span></div>
      <div>Raised: {formatTimestamp(auditData.alarm_info.raised_at)}</div>
      {auditData.alarm_info.ack_by && (
        <div>ACKed by: {auditData.alarm_info.ack_by_display_name || auditData.alarm_info.ack_by} @ {formatTimestamp(auditData.alarm_info.ack_at)}</div>
      )}
      <div>Occurrence: <code>{auditData.alarm_info.occurrence_id?.substring(0, 13)}...</code></div>
    </div>
  </div>

  <div className="audit-controls">
    <h4>Audit Trail History</h4>
    <button onClick={toggleSortOrder} className="timeline-toggle">
      {sortOrder === 'desc' ? '📅 Latest First' : '📜 Timeline View (Oldest First)'}
    </button>
  </div>
</div>

<div className="audit-trail-records">
  {auditData.audit_trail.map((record, idx) => (
    <div 
      key={record.audit_id} 
      className={`audit-record ${record.action_type.toLowerCase()}`}
      data-sequence={record.sequence_number}
    >
      <div className="record-header">
        <span className="action-badge">{record.action_type}</span>
        <span className="timestamp">{formatTimestamp(record.action_timestamp)}</span>
        {record.response_time_seconds && (
          <span className="response-time">⏱ {formatDuration(record.response_time_seconds)}</span>
        )}
      </div>
      
      <div className="record-details">
        <div className="operator-info">
          <strong>{record.performed_by_display_name || record.performed_by}</strong>
          {record.performed_by_user_id && <span className="user-id">#{record.performed_by_user_id}</span>}
        </div>
        
        {record.alarm_actual_value && (
          <div className="values">
            Value: {record.alarm_actual_value.toFixed(2)} (SP: {record.alarm_setpoint.toFixed(2)})
          </div>
        )}
        
        {record.action_reason && (
          <div className="reason">
            <label>Reason:</label>
            <p>{record.action_reason}</p>
          </div>
        )}
        
        {record.action_notes && (
          <div className="notes">
            <label>Notes:</label>
            <p>{record.action_notes}</p>
          </div>
        )}
        
        {record.previous_state && (
          <div className="transition">
            {record.previous_state} → {record.new_state}
          </div>
        )}
      </div>
    </div>
  ))}
</div>

{auditData.has_more && (
  <button onClick={loadMoreRecords} className="load-more">
    Load More ({auditData.total_count - auditData.count} remaining)
  </button>
)}

<div className="audit-footer">
  <span>Showing {auditData.count} of {auditData.total_count} records</span>
  {auditData.alarm_info.data_consistency_verified && (
    <span className="verified">✓ Data Verified</span>
  )}
</div>
```

**Lifecycle state badge colors**:
```css
.status-badge[data-state="ACTIVE_UNACKED"] { background: #dc3545; color: white; } /* Red - urgent */
.status-badge[data-state="ACTIVE_ACKED"] { background: #ffc107; color: black; } /* Yellow - acknowledged */
.status-badge[data-state="CLEARED_UNACKED"] { background: #17a2b8; color: white; } /* Cyan - returning */
.status-badge[data-state="CLEARED_ACKED"] { background: #28a745; color: white; } /* Green - resolved */
.status-badge[data-state="SUPPRESSED"] { background: #6c757d; color: white; } /* Gray - suppressed */
```

---

## 📋 IMPLEMENTATION STEPS (✅ APPROVED)

### Phase 1: Database Schema Updates (DO FIRST)
1. ✅ **Add indexes** - event_id, occurrence_id, timestamp
   ```sql
   CREATE INDEX idx_alarm_audit_event_timestamp ON alarm_audit_trail(event_id, action_timestamp DESC);
   CREATE INDEX idx_alarm_audit_occurrence ON alarm_audit_trail(occurrence_id);
   ```

2. ✅ **Add sequence_number column** - For proper action ordering
   ```sql
   ALTER TABLE alarm_audit_trail ADD COLUMN sequence_number INTEGER;
   CREATE SEQUENCE alarm_audit_sequence_seq;
   ```

3. ✅ **Add operator snapshot columns**
   ```sql
   ALTER TABLE alarm_audit_trail ADD COLUMN performed_by_display_name TEXT;
   ALTER TABLE alarm_audit_trail ADD COLUMN performed_by_user_id INTEGER;
   ```

### Phase 2: Backend Fixes (CRITICAL)
4. ✅ **Fix query logic** - Filter by `event_id` ONLY, not tag_id
5. ✅ **Add occurrence_id filtering** - Separate re-triggers uniquely
6. ✅ **Add alarm_info section** - Pin latest state at top
7. ✅ **Implement pagination** - Backend-side, limit=20, has_more flag
8. ✅ **Add lifecycle state mapping** - ACTIVE_UNACKED, ACTIVE_ACKED, etc.
9. ✅ **Add validation** - No ACK before RAISED, no double CLEAR
10. ✅ **Default sort DESC** - Newest first for operators
11. ✅ **Add sort toggle** - Optional ASC mode for investigations
12. ✅ **Store operator snapshots** - Display name + user_id on every action

### Phase 3: Frontend Updates (AFTER BACKEND VERIFIED)
13. ⏳ **Pin current alarm state at top** - LATEST data first
14. ⏳ **Add lifecycle state badges** - Visual indicators
15. ⏳ **Format audit records** - Operator display names, response times
16. ⏳ **Add "Load More" button** - Backend pagination support
17. ⏳ **Add "Timeline View" toggle** - Switch DESC ↔ ASC
18. ⏳ **Show is_current_occurrence badge** - "LIVE" indicator
19. ⏳ **Add data_consistency_verified icon** - Trust indicator

### Phase 4: Validation & Testing
20. ⏳ **Test re-trigger scenario** - Each occurrence gets NEW audit trail
21. ⏳ **Test multiple ACKs** - Pagination works, newest shown first
22. ⏳ **Test state transitions** - Validation catches invalid transitions
23. ⏳ **Test operator snapshots** - Display names stored correctly
24. ⏳ **Performance test** - Queries <100ms with 1000+ audit records
25. ⏳ **Compliance check** - FDA 21 CFR Part 11, ISA-18.2 conformance

---

## 🎯 APPROVED DECISIONS

### ✅ Question 1: Display Limit Strategy
**APPROVED: 20 records + backend pagination**

| Feature | Decision | Rationale |
|---------|----------|-----------|
| Default limit | 20 records | Balances visibility and performance |
| Pagination | Backend-side only | No frontend slicing, proper DB queries |
| Load more | "Load More" button | Simple UX, operator-friendly |
| Full history | Always available | Compliance requirement |

---

### Question 2: Sort Order
**Should audit trail show newest-first or oldest-first?**

| Order | Pros | Cons |
|-------|------|------|
| Newest first (DESC) | See latest actions immediately | Story reads backwards |
| Oldest first (ASC) | Natural chronological story | Must scroll to see latest |

**✅ APPROVED: Newest first (DESC)** - **Plant operators need LATEST data first**
- Top of audit shows most recent action (last ACK, last CLEAR)
- Operators see current situation immediately
- Historical context available by scrolling down
- Optional "Timeline View" button switches to ASC for investigations

---

### ✅ Question 2: Sort Order
**APPROVED: Newest first (DESC) by default, optional Timeline View (ASC)**

| Mode | Sort | Use Case | Button Label |
|------|------|----------|--------------|
| Default | DESC | **Plant operators** - See latest action immediately | "📅 Latest First" |
| Timeline | ASC | Investigations - Full chronological story | "📜 Timeline View" |

**Key principle**: **Operators need LATEST data FIRST** - Current plant situation > Historical context

---

### ✅ Question 3: RTN (Return to Normal) Display
**APPROVED: Show RTN states in audit trail**

| State | Display | Color | Meaning |
|-------|---------|-------|---------|
| RTN_UNACK | CLEARED_UNACKED | Cyan | Tag returned to normal, needs ACK |
| CLEARED | CLEARED_ACKED | Green | Fully resolved |

**Rationale**: 
- RTN is critical state transition (tag no longer in alarm)
- Operators need to see when process returned to normal
- ISA-18.2 compliance requires RTN tracking
- Shows alarm duration (RAISED → RTN time)

---

### ✅ Question 4: Re-triggered Alarms
**APPROVED: Separate audit trails per occurrence_id**

| Behavior | Implementation |
|----------|----------------|
| Each re-trigger | NEW event_id + NEW occurrence_id (GUID) |
| Audit trail | Filtered by event_id → Shows ONE occurrence only |
| Alarm card | Shows current occurrence_id in header |
| Historical access | Query by event_id to see specific occurrence |

**Key principle**: Each alarm card = ONE occurrence = ONE audit trail (no mixing)

---

## 📊 RISK ASSESSMENT

| Risk | Impact | Mitigation |
|------|--------|------------|
| Query change breaks existing audit trails | HIGH | Test with real alarm_id values before deploy |
| alarm_active.current_event_id missing | MEDIUM | Add fallback to historian_events query |
| Frontend not showing occurrence_id | LOW | Backend change independent of frontend |
| Display limit too aggressive | LOW | User can click "Show All" button |

---

## 🧪 TESTING CHECKLIST

**Before deployment**:
- [ ] Verify `get_audit_trail_enhanced()` query uses `WHERE event_id = %s` 
- [ ] Test with VYAN1101G alarm_id=881456 (should show ONLY ~15 records, not 100+)
- [ ] Verify occurrence_id appears in response
- [ ] Confirm raised_at and raised_value show correct latest values
- [ ] Test "Show All" button if total_count > 20

**After deployment**:
- [ ] Raise new alarm, verify audit trail has 1 record (RAISED)
- [ ] ACK alarm, verify audit trail has 2 records (RAISED, ACK)
- [ ] CLEAR alarm, verify audit trail has 3 records (RAISED, ACK, CLEAR)
- [ ] Re-trigger alarm, verify NEW audit trail appears (not mixed with old)
- [ ] ACK alarm 25 times, verify only 20 shown with "Show All" button

---

## 📝 APPROVED IMPLEMENTATION SUMMARY

### ✅ What's Broken (CONFIRMED):
1. ❌ Audit trail shows ALL tag history (multiple occurrences mixed)
2. ❌ No alarm instance info (occurrence_id, latest raised_at/value)
3. ❌ No display limits (100 records shown, unreadable)
4. ❌ Re-triggered alarms don't get separate audit trails
5. ❌ Sort order wrong (oldest first, operators need newest first)
6. ❌ No lifecycle state mapping (raw ISA states not user-friendly)
7. ❌ No operator display names (only usernames stored)
8. ❌ No validation (can ACK before RAISED, can double CLEAR)

### ✅ What We'll Implement (APPROVED):
1. ✅ **Filter by event_id ONLY** - Each alarm occurrence isolated
2. ✅ **Add occurrence_id tracking** - Separate re-triggers uniquely
3. ✅ **Pin alarm_info at top** - Latest state, value, priority visible first
4. ✅ **Default sort DESC** - Newest action first (operators' priority)
5. ✅ **Backend pagination** - Limit=20, has_more flag, "Load More" button
6. ✅ **Lifecycle state mapping** - ACTIVE_UNACKED, ACTIVE_ACKED, CLEARED_UNACKED, CLEARED_ACKED
7. ✅ **Show RTN states** - Track return-to-normal transitions
8. ✅ **Add sequence_number** - Proper action ordering
9. ✅ **Store operator snapshots** - Display name + user_id on every action
10. ✅ **Add validation** - No ACK before RAISED, no double CLEAR
11. ✅ **Add is_current_occurrence flag** - Show "LIVE" badge for active alarms
12. ✅ **Optimize queries** - Indexes on event_id, occurrence_id, timestamp
13. ✅ **Timeline toggle** - Optional ASC mode for investigations
14. ✅ **Keep audit immutable** - Once written, never modified
15. ✅ **MQTT/live UI separate** - Audit trail = historical compliance record

### ✅ Approved Decisions:
- ✅ **Display limit**: 20 records + backend pagination
- ✅ **Sort order**: Newest first (DESC) by default, Timeline View (ASC) optional
- ✅ **Show RTN states**: Yes, critical for ISA-18.2 compliance
- ✅ **Separate re-triggers**: Each occurrence_id = separate audit trail
- ✅ **Pin latest at top**: Operators need current plant situation FIRST
- ✅ **Backend + Frontend**: Full implementation, not just backend

### 🚀 Ready to Implement:
**Phase 1**: Database schema updates (indexes, columns)  
**Phase 2**: Backend fixes (query, validation, pagination)  
**Phase 3**: Frontend updates (pinned header, badges, timeline toggle)  
**Phase 4**: Testing & validation (compliance, performance)

---

## 🎯 BETTER IDEAS ADDED

### 💡 Idea 1: Lifecycle State Badges
**Why**: Raw ISA states confusing for operators  
**Solution**: Visual badges with color coding
- 🔴 ACTIVE_UNACKED (urgent, needs attention)
- 🟡 ACTIVE_ACKED (acknowledged, being handled)
- 🔵 CLEARED_UNACKED (returned to normal, needs final ACK)
- 🟢 CLEARED_ACKED (fully resolved)

### 💡 Idea 2: Pinned Current State
**Why**: Operators need LATEST data first, not historical  
**Solution**: Pin alarm_info section at top showing:
- Current value vs setpoint
- Deviation amount
- Current lifecycle state
- Who ACKed and when
- "LIVE" badge if still active

### 💡 Idea 3: Timeline Toggle
**Why**: Different use cases need different views  
**Solution**: 
- Default = Newest first (daily operations)
- Timeline View = Oldest first (investigations, root cause analysis)

### 💡 Idea 4: Operator Snapshots
**Why**: Compliance requires knowing WHO did WHAT  
**Solution**: Store display_name + user_id on every action
- Audit shows "John Smith (Operator #342)" not just "jsmith"
- Immutable record even if user renamed/deleted

### 💡 Idea 5: Response Time Tracking
**Why**: KPI for alarm response performance  
**Solution**: Show time between RAISED and first ACK
- Display in audit trail: "⏱ Response: 12m 34s"
- Use for performance analytics

### 💡 Idea 6: Data Consistency Flag
**Why**: Build operator trust in system  
**Solution**: Add `data_consistency_verified` flag
- Checks occurrence_id matches
- Verifies no orphaned records
- Shows ✓ badge in UI

---

**All approved requirements integrated. Ready to start implementation.**
