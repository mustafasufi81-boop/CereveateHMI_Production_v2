import psycopg2
conn = psycopg2.connect(dbname='Automation_DB', user='cereveate', password='cereveate@222', host='localhost')
cur = conn.cursor()

# 1. tag_master columns
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='historian_meta' AND table_name='tag_master' ORDER BY ordinal_position")
cols = [r[0] for r in cur.fetchall()]
print("tag_master columns:", cols)

# 2. How many alarm-enabled tags
cur.execute("SELECT COUNT(*) FROM historian_meta.tag_master WHERE alarm_enabled = true")
print(f"\nAlarm-enabled tags: {cur.fetchone()[0]}")

# 3. Find the live value column name
value_col = None
for c in ['current_value', 'last_value', 'tag_value', 'raw_value']:
    if c in cols:
        value_col = c
        break
print(f"Value column: {value_col}")

# 4. Check recent alarm_active records
cur.execute("SELECT COUNT(*) FROM historian_raw.alarm_active")
print(f"alarm_active count: {cur.fetchone()[0]}")

# 5. Check historian_events in last 5 min
cur.execute("""
    SELECT event_type, COUNT(*), MAX(time) 
    FROM historian_raw.historian_events 
    WHERE time > NOW() - INTERVAL '5 minutes'
    GROUP BY event_type ORDER BY MAX(time) DESC
""")
rows = cur.fetchall()
print("\nRecent historian_events (last 5 min):")
for r in rows:
    print(f"  {r[0]}: count={r[1]}, latest={r[2]}")
if not rows:
    print("  NONE - C# alarm engine may still be connecting to DB")

conn.close()
