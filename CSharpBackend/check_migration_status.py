import psycopg2

conn = psycopg2.connect(host='localhost', port=5432, dbname='Automation_DB',
                        user='cereveate', password='cereveate@222')
cur = conn.cursor()

print("=== 1. alarm_active table exists? ===")
cur.execute("SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_schema='historian_raw' AND table_name='alarm_active')")
print(cur.fetchone()[0])

print("\n=== 2. historian_events NEW columns exist? ===")
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='historian_raw' AND table_name='historian_events' AND column_name IN ('alarm_level','occurrence_id','instance_seq') ORDER BY column_name")
found = [r[0] for r in cur.fetchall()]
for col in ['alarm_level','occurrence_id','instance_seq']:
    print(f"  {col}: {'EXISTS' if col in found else 'MISSING'}")

print("\n=== 3. tag_master alarm_onset_delay_s exists? ===")
cur.execute("SELECT EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema='historian_meta' AND table_name='tag_master' AND column_name='alarm_onset_delay_s')")
print(cur.fetchone()[0])

print("\n=== 4. Blocking rows (32654,32655,32656) status ===")
cur.execute("SELECT event_id, alarm_state FROM historian_raw.historian_events WHERE event_id IN (32654,32655,32656)")
rows = cur.fetchall()
if rows:
    for r in rows: print(f"  event_id={r[0]}  alarm_state={r[1]}")
else:
    print("  rows not found")

conn.close()
