"""
Fix: Clear the 3 Python test rows (event_id 32654-32656) that were inserted during
schema testing. These rows are blocking alarm evaluation — LoadActiveAlarmsFromDbAsync
loaded event_id=32656 as 'ACTIVE' for Random.Real4, so the service thinks the alarm is
already raised and never calls RaiseAlarmAsync.
"""
import psycopg2

conn = psycopg2.connect(
    host='localhost', port=5432,
    dbname='Automation_DB', user='cereveate', password='cereveate@222'
)
conn.autocommit = False
cur = conn.cursor()

# Mark test rows as CLEARED so RefreshRuntimeStatesFromDbAsync removes them from memory
cur.execute("""
    UPDATE historian_raw.historian_events
    SET    alarm_state = 'CLEARED'
    WHERE  event_id IN (32654, 32655, 32656)
      AND  tag_id = 'Random.Real4'
""")
rows = cur.rowcount
print(f"Updated {rows} test row(s) to CLEARED")

conn.commit()
conn.close()

print("Done. The runtime state refresh (every 30s) will now remove Random.Real4 from")
print("in-memory state and the next evaluation cycle will raise a REAL alarm to the DB.")
