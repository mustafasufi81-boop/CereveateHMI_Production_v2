import psycopg2

conn = psycopg2.connect(host='localhost', port=5432, dbname='Automation_DB',
                        user='cereveate', password='cereveate@222')
conn.autocommit = False
cur = conn.cursor()

# Tags that are ACTUALLY in OPC right now (from diagnostics: inPool=true)
live_tags = ['Random.Real4', 'Triangle Waves.Real4', 'Bucket Brigade.Real4']

# Count what we're about to clear
cur.execute("""
    SELECT COUNT(*) FROM historian_raw.historian_events
    WHERE alarm_state = 'ACTIVE'
    AND tag_id NOT IN %s
""", (tuple(live_tags),))
count = cur.fetchone()[0]
print(f"Stale ACTIVE alarms to clear: {count}")

# Clear them
cur.execute("""
    UPDATE historian_raw.historian_events
    SET alarm_state   = 'CLEARED',
        cleared_at    = NOW(),
        cleared_by    = 'SYSTEM_CLEANUP',
        clear_reason  = 'Tag not in OPC pool - stale simulation data'
    WHERE alarm_state = 'ACTIVE'
    AND tag_id NOT IN %s
""", (tuple(live_tags),))
print(f"Cleared: {cur.rowcount} rows")

# Also clear interlock_state_tracking for non-live tags
cur.execute("""
    UPDATE historian_raw.interlock_state_tracking
    SET interlock_state = 'CLEARED',
        event_time      = NOW()
    WHERE interlock_state NOT IN ('CLEARED', 'INACTIVE')
    AND interlock_tag_id NOT IN %s
""", (tuple(live_tags),))
print(f"Cleared interlock rows: {cur.rowcount}")

conn.commit()
print("DONE - database cleaned")
conn.close()
