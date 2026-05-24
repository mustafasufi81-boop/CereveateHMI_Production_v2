import psycopg2
conn = psycopg2.connect(host='localhost', dbname='Automation_DB', user='cereveate', password='cereveate@222')
cur = conn.cursor()
cur.execute("""
    SELECT column_name, data_type, is_nullable
    FROM information_schema.columns
    WHERE table_schema='historian_raw' AND table_name='interlock_state_tracking'
    ORDER BY ordinal_position
""")
print("=== interlock_state_tracking ===")
for r in cur.fetchall():
    print(r)

cur.execute("""
    SELECT column_name, data_type
    FROM information_schema.columns
    WHERE table_schema='historian_meta' AND table_name='tag_master'
      AND column_name IN ('interlock_type','is_trip_initiator','causes_trip_on_tag',
                          'trip_category','trip_time_window_seconds','alarm_enabled',
                          'alarm_deadband','alarm_priority')
    ORDER BY column_name
""")
print("=== tag_master interlock cols ===")
for r in cur.fetchall():
    print(r)
conn.close()
