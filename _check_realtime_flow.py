import psycopg2
from datetime import datetime, timedelta

conn = psycopg2.connect(
    host="localhost", port=5432, 
    database="Automation_DB", user="cereveate", password="cereveate@222"
)
cur = conn.cursor()

print("=" * 80)
print("CHECKING REAL-TIME DATA FLOW")
print("=" * 80)

# Check for very recent data
cur.execute("""
    SELECT tag_id, time, value_num 
    FROM historian_raw.historian_timeseries 
    WHERE time > NOW() - INTERVAL '30 seconds'
    ORDER BY time DESC 
    LIMIT 10
""")
rows = cur.fetchall()

print(f"\n[1] Data in last 30 seconds: {len(rows)} records")
if rows:
    print("Recent values:")
    for tag_id, time, value_num in rows[:5]:
        print(f"  {tag_id}: {time} = {value_num}")
else:
    print("  ❌ NO DATA in last 30 seconds!")

# Check latest_value table update time
cur.execute("""
    SELECT MAX(updated_at) as latest_update
    FROM historian_raw.historian_latest_value
""")
latest_update = cur.fetchone()[0]
print(f"\n[2] historian_latest_value last updated: {latest_update}")
print(f"    Time difference from now: {datetime.now(latest_update.tzinfo) - latest_update if latest_update else 'N/A'}")

# Check if there's a trigger or process updating latest_value
cur.execute("""
    SELECT tgname, tgtype, proname 
    FROM pg_trigger t
    JOIN pg_proc p ON t.tgfoid = p.oid
    JOIN pg_class c ON t.tgrelid = c.oid
    WHERE c.relname = 'historian_timeseries'
""")
triggers = cur.fetchall()
print(f"\n[3] Triggers on historian_timeseries: {len(triggers)}")
for trigger_name, trigger_type, proc_name in triggers:
    print(f"  - {trigger_name} ({proc_name})")

cur.close()
conn.close()
print("\n" + "=" * 80)
