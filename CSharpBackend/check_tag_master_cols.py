import psycopg2
conn = psycopg2.connect(host='localhost', port=5432, dbname='Automation_DB', user='cereveate', password='cereveate@222')
cur = conn.cursor()

# Check what columns actually exist in tag_master
cur.execute("""
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'historian_meta' AND table_name = 'tag_master'
ORDER BY ordinal_position
""")
cols = cur.fetchall()
print(f"tag_master columns ({len(cols)} total):")
for c in cols:
    print(f"  {c[0]:<40} {c[1]}")

# Check specifically for the 3 columns the C# code queries
missing = []
col_names = [c[0] for c in cols]
for check in ['is_trip_initiator', 'causes_trip_on_tag', 'trip_category', 'alarm_deadband']:
    status = '✅ EXISTS' if check in col_names else '❌ MISSING'
    print(f"\n  {check}: {status}")
    if check not in col_names:
        missing.append(check)

if missing:
    print(f"\n⚠️  FOUND ROOT CAUSE: {missing} are missing from tag_master!")
    print("  AlarmSetpointCacheService SQL fails → 0 setpoints loaded → 0 alarms evaluated")
else:
    print("\n✅ All columns exist — problem is elsewhere")

conn.close()
