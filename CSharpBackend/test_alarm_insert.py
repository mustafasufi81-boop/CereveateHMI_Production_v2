"""
Tests exact same INSERT that AlarmEvaluationService.RaiseAlarmAsync does.
Prints exact error if it fails.
"""
import psycopg2
from datetime import datetime, timezone

conn = psycopg2.connect(
    host="localhost", port=5432,
    dbname="Automation_DB",
    user="cereveate", password="cereveate@222"
)
conn.autocommit = False
cur = conn.cursor()

try:
    # Step 1: historian_events INSERT (exact columns C# sends)
    cur.execute("""
        INSERT INTO historian_raw.historian_events
            (time, tag_id, event_type, severity, message,
             alarm_state, alarm_priority, alarm_setpoint, alarm_actual_value)
        VALUES
            (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING event_id
    """, (
        datetime.now(timezone.utc),
        'Random.Real4',
        'ALARM_RAISED_H',
        1,
        'Random.Real4 exceeded High limit: 23000 (setpoint: 20000)',
        'ACTIVE',
        1,
        20000.0,
        23000.0,
    ))
    event_id = cur.fetchone()[0]
    print(f"Step 1 OK - event_id={event_id}")

    # Step 2: alarm_audit_trail INSERT (exact columns C# sends)
    cur.execute("""
        INSERT INTO historian_raw.alarm_audit_trail
            (event_id, tag_id, event_type, action_type, performed_by,
             previous_state, new_state, alarm_priority, alarm_actual_value, alarm_setpoint)
        VALUES
            (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        event_id,
        'Random.Real4',
        'ALARM_RAISED_H',
        'RAISED',
        'SYSTEM',
        'NORMAL',
        'ACTIVE',
        1,
        23000.0,
        20000.0,
    ))
    print("Step 2 OK - audit trail inserted")

    conn.commit()
    print(f"\nSUCCESS - event_id={event_id} committed to DB")

except Exception as e:
    conn.rollback()
    print(f"\nFAILED - exact error: {e}")
finally:
    conn.close()
