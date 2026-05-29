# Alarm Audit Trail Implementation Log
**Date**: May 28, 2026  
**Status**: In Progress  
**Objective**: Fix audit trail to show one alarm occurrence per event_id

---

## Phase 1: Investigation Complete ✅

### Findings:
1. ✅ **AlarmAuditDAO.get_audit_trail_enhanced()** - Already correctly filters by `event_id`
   - Location: `mqtt_subscriber_service/src/database/alarm_audit_dao.py` line 289
   - Query uses: `WHERE event_id = %s` (CORRECT)
   
2. ✅ **alarm_controller.py get_alarm_audit_trail()** - Calls DAO correctly
   - Location: `HMI/controllers/alarm_controller.py` line 1233
   - Passes `event_id=alarm_id` to DAO (CORRECT)

3. ✅ **v_alarm_audit_trail view** - Properly joins tag_master
   - Location: `mqtt_subscriber_service/sql/create_alarm_audit_trail.sql`
   - Uses window functions for timing calculations

4. ❌ **MISSING FEATURES** (what needs to be added):
   - No alarm_info section (occurrence_id, current state, latest value)
   - No pagination (hardcoded limit=100)
   - No sort_order parameter (always DESC)
   - No lifecycle state mapping
   - No has_more flag for UI
   - No count_audit_records() method

---

## Phase 2: Database Schema Updates

### Step 2.1: Check Current Schema ⏳
**Action**: Verify alarm_audit_trail table structure

**SQL to run**:
```sql
-- Check if occurrence_id column exists
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_schema = 'historian_raw' 
  AND table_name = 'alarm_audit_trail'
ORDER BY ordinal_position;

-- Check existing indexes
SELECT indexname, indexdef 
FROM pg_indexes 
WHERE schemaname = 'historian_raw' 
  AND tablename = 'alarm_audit_trail';
```

### Step 2.2: Add Missing Columns (if needed)
**Action**: Add occurrence_id if not present, add operator snapshot columns

**SQL to run**:
```sql
-- Add occurrence_id column (if missing)
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema='historian_raw' 
          AND table_name='alarm_audit_trail' 
          AND column_name='occurrence_id'
    ) THEN
        ALTER TABLE historian_raw.alarm_audit_trail 
        ADD COLUMN occurrence_id UUID;
        
        RAISE NOTICE 'Added occurrence_id column';
    END IF;
END $$;

-- Add sequence_number column (if missing)
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema='historian_raw' 
          AND table_name='alarm_audit_trail' 
          AND column_name='sequence_number'
    ) THEN
        ALTER TABLE historian_raw.alarm_audit_trail 
        ADD COLUMN sequence_number INTEGER;
        
        RAISE NOTICE 'Added sequence_number column';
    END IF;
END $$;

-- Add operator snapshot columns (if missing)
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema='historian_raw' 
          AND table_name='alarm_audit_trail' 
          AND column_name='performed_by_display_name'
    ) THEN
        ALTER TABLE historian_raw.alarm_audit_trail 
        ADD COLUMN performed_by_display_name TEXT,
        ADD COLUMN performed_by_user_id INTEGER;
        
        RAISE NOTICE 'Added operator snapshot columns';
    END IF;
END $$;
```

### Step 2.3: Add Performance Indexes
**Action**: Create indexes for fast queries

**SQL to run**:
```sql
-- Index on (event_id, action_timestamp DESC) for single alarm queries
CREATE INDEX IF NOT EXISTS idx_alarm_audit_event_timestamp 
ON historian_raw.alarm_audit_trail(event_id, action_timestamp DESC);

-- Index on occurrence_id for occurrence-based filtering
CREATE INDEX IF NOT EXISTS idx_alarm_audit_occurrence 
ON historian_raw.alarm_audit_trail(occurrence_id);

-- Composite index for pagination queries
CREATE INDEX IF NOT EXISTS idx_alarm_audit_event_sequence 
ON historian_raw.alarm_audit_trail(event_id, sequence_number);

-- Comment on indexes
COMMENT ON INDEX historian_raw.idx_alarm_audit_event_timestamp IS 
'Performance index for fetching audit trail by event_id with descending timestamp order';
```

---

## Phase 3: Backend Implementation

### Step 3.1: Add count_audit_records() Method
**File**: `mqtt_subscriber_service/src/database/alarm_audit_dao.py`

**Action**: Add method to count total records for pagination

**Code to add** (after get_audit_trail_enhanced method, around line 450):
```python
def count_audit_records(self, event_id: Optional[int] = None, tag_id: Optional[str] = None) -> int:
    """
    Count total audit records for pagination
    
    Args:
        event_id: Filter by specific alarm event_id
        tag_id: Filter by tag_id
        
    Returns:
        Total count of matching records
    """
    where_clauses = []
    params = []
    
    if event_id is not None:
        where_clauses.append("event_id = %s")
        params.append(event_id)
    
    if tag_id is not None:
        where_clauses.append("tag_id = %s")
        params.append(tag_id)
    
    where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""
    
    query = f"""
        SELECT COUNT(*) 
        FROM historian_raw.alarm_audit_trail
        {where_sql}
    """
    
    cursor = None
    try:
        if self.use_direct_connection:
            cursor = self._get_cursor()
            cursor.execute(query, tuple(params))
            result = cursor.fetchone()
            cursor.close()
            count = result[0] if result else 0
        else:
            with self._get_cursor() as cur:
                cur.execute(query, tuple(params))
                result = cur.fetchone()
                count = result[0] if result else 0
        
        return count
        
    except Exception as e:
        if self.use_direct_connection and cursor:
            try:
                cursor.close()
            except:
                pass
        logger.error(f"Failed to count audit records: {e}")
        return 0
```

### Step 3.2: Update get_audit_trail_enhanced() Method
**File**: `mqtt_subscriber_service/src/database/alarm_audit_dao.py`

**Action**: Add sort_order and offset parameters

**Changes needed**:
1. Add `sort_order` parameter (default='desc')
2. Add `offset` parameter (default=0)
3. Update ORDER BY clause to use sort_order
4. Add OFFSET to query

**Modified signature** (line 289):
```python
def get_audit_trail_enhanced(self, 
                            event_id: Optional[int] = None,
                            tag_id: Optional[str] = None,
                            limit: int = 100,
                            offset: int = 0,
                            sort_order: str = 'desc') -> List[Dict[str, Any]]:
```

**Modified query ORDER BY** (line 325):
```python
sort_direction = 'DESC' if sort_order.lower() == 'desc' else 'ASC'
query = f"""
    SELECT ...
    FROM historian_raw.v_alarm_audit_trail
    {where_sql}
    ORDER BY action_timestamp {sort_direction}
    LIMIT %s OFFSET %s
"""

params.extend([limit, offset])
```

### Step 3.3: Update get_alarm_audit_trail() Controller
**File**: `HMI/controllers/alarm_controller.py`

**Action**: Add alarm_info section, pagination, and lifecycle mapping

**Changes needed** (line 1211):
1. Get query parameters (page, page_size, sort)
2. Query alarm_active for current alarm info
3. Call count_audit_records()
4. Add lifecycle state mapping function
5. Return enhanced response with alarm_info

---

## Phase 4: Testing Plan

### Test 4.1: Database Schema Verification
- [ ] Verify occurrence_id column exists
- [ ] Verify indexes created successfully
- [ ] Check index usage with EXPLAIN ANALYZE

### Test 4.2: DAO Method Testing
- [ ] Test count_audit_records() with event_id
- [ ] Test get_audit_trail_enhanced() with sort='desc'
- [ ] Test get_audit_trail_enhanced() with sort='asc'
- [ ] Test pagination (offset=0, offset=20)

### Test 4.3: Controller Testing
- [ ] Test /api/alarms/audit/881456 returns alarm_info
- [ ] Test alarm_info.occurrence_id present
- [ ] Test has_more flag correct
- [ ] Test page parameter works
- [ ] Test sort parameter works

### Test 4.4: End-to-End Scenarios
- [ ] Raise new alarm → verify 1 audit record (RAISED)
- [ ] ACK alarm → verify 2 records (RAISED, ACK)
- [ ] CLEAR alarm → verify 3 records (RAISED, ACK, CLEAR)
- [ ] Re-trigger alarm → verify NEW event_id, separate audit trail
- [ ] ACK alarm 25 times → verify pagination shows 20, has_more=true

---

## Implementation Progress

### ✅ Completed:
- [x] Phase 1: Investigation and code review

### ⏳ In Progress:
- [ ] Phase 2: Database schema updates

### 🔜 Pending:
- [ ] Phase 3: Backend implementation
- [ ] Phase 4: Testing

---

## Notes

- No hardcoding - all values configurable
- No code disturbance - add methods, don't modify existing logic
- Backward compatible - existing code continues to work
- Audit after done - log all changes

---

**Next Step**: Execute Step 2.1 - Check current schema
