import psycopg2
import uuid
from datetime import datetime, timezone

c = psycopg2.connect(dbname='Automation_DB', user='cereveate', password='cereveate@222', host='localhost')
c.autocommit = False
cur = c.cursor()

print("=== TEST EXACT RaiseAsync INSERT ===")

# Check sequence exists
try:
    cur.execute("SELECT nextval('historian_raw.alarm_transition_seq')")
    seq = cur.fetchone()[0]
    print(f"alarm_transition_seq: OK, next={seq}")
    c.rollback()
except Exception as e:
    print(f"alarm_transition_seq MISSING: {e}")
    c.rollback()

# Test the exact historian_events INSERT from AlarmStateManager.RaiseAsync
try:
    occ_id = str(uuid.uuid4())
    cur.execute("""
        INSERT INTO historian_raw.historian_events
            (time, tag_id, event_type, severity, message,
             alarm_state, alarm_priority, alarm_setpoint, alarm_actual_value,
             alarm_level, occurrence_id, instance_seq, transition_seq)
        VALUES
            (%s, %s, %s, %s, %s,
             'ACTIVE_UNACK', %s, %s, %s,
             %s, %s, %s,
             nextval('historian_raw.alarm_transition_seq'))
        RETURNING event_id, transition_seq
    """, (
        datetime.now(timezone.utc),
        'Triangle Waves.Real4',
        'ALARM_RAISED_L',
        2, 'Test alarm raise',
        2, 25.0, 12.7,
        'Low', occ_id, 1
    ))
    row = cur.fetchone()
    print(f"historian_events INSERT: OK  event_id={row[0]}, transition_seq={row[1]}")
    event_id = row[0]
    trans_seq = row[1]
except Exception as e:
    print(f"historian_events INSERT FAILED: {e}")
    c.rollback()
    c.close()
    exit()

# Test the exact alarm_active UPSERT
try:
    cur.execute("""
        INSERT INTO historian_raw.alarm_active
            (alarm_key, tag_id, level, alarm_state, current_event_id,
             occurrence_id, instance_seq, raised_at, raised_value,
             setpoint_value, priority, transition_seq, updated_at)
        VALUES
            (%s, %s, %s, 'ACTIVE_UNACK', %s,
             %s, %s, %s, %s,
             %s, %s, %s, NOW())
        ON CONFLICT (alarm_key) DO UPDATE
            SET alarm_state      = 'ACTIVE_UNACK',
                current_event_id = EXCLUDED.current_event_id,
                updated_at       = NOW()
    """, (
        'Triangle Waves.Real4::Low',
        'Triangle Waves.Real4',
        'Low', event_id,
        occ_id, 1,
        datetime.now(timezone.utc), 12.7,
        25.0, 2, trans_seq
    ))
    print("alarm_active UPSERT: OK")
except Exception as e:
    print(f"alarm_active UPSERT FAILED: {e}")
    c.rollback()
    c.close()
    exit()

c.rollback()  # clean up — don't actually write
print("\nAll steps passed. Rolling back test data.")
c.close()
