import psycopg2

conn = psycopg2.connect(host='localhost', port=5432, dbname='Automation_DB',
                        user='cereveate', password='cereveate@222')
cur = conn.cursor()

print("=== historian_raw.historian_events — all columns ===")
cur.execute("""
    SELECT column_name, data_type, is_nullable
    FROM information_schema.columns
    WHERE table_schema = 'historian_raw' AND table_name = 'historian_events'
    ORDER BY ordinal_position
""")
for r in cur.fetchall():
    print(r)

print()
print("=== historian_events CHECK constraints ===")
cur.execute("""
    SELECT conname, pg_get_constraintdef(c.oid)
    FROM pg_constraint c
    JOIN pg_class t ON t.oid = c.conrelid
    JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'historian_raw' AND t.relname = 'historian_events' AND c.contype = 'c'
""")
for r in cur.fetchall():
    print(r)

print()
print("=== alarm_active table exists? ===")
cur.execute("""
    SELECT EXISTS(
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'historian_raw' AND table_name = 'alarm_active'
    )
""")
print(cur.fetchone())

print()
print("=== historian_meta.tag_master — alarm columns ===")
cur.execute("""
    SELECT column_name, data_type
    FROM information_schema.columns
    WHERE table_schema = 'historian_meta' AND table_name = 'tag_master'
      AND column_name LIKE 'alarm%'
    ORDER BY column_name
""")
for r in cur.fetchall():
    print(r)

print()
print("=== sample of current alarm_state values in historian_events ===")
cur.execute("""
    SELECT alarm_state, COUNT(*) FROM historian_raw.historian_events
    WHERE alarm_state IS NOT NULL
    GROUP BY alarm_state ORDER BY alarm_state
""")
for r in cur.fetchall():
    print(r)

conn.close()
