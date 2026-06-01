import json, psycopg2
from datetime import datetime, timedelta

with open('config.json', 'r') as f:
    config = json.load(f)

db = config['database']
conn = psycopg2.connect(host=db['host'], port=db['port'], database=db['database'], user=db['user'], password=db['password'])
cur = conn.cursor()

print("\n🔍 CHECKING IF SYSTEM IS COLLECTING DATA\n")

# 1. Find what historian tables exist
print("1. Finding historian data tables...")
cur.execute("""
    SELECT schemaname, tablename 
    FROM pg_tables 
    WHERE schemaname LIKE '%hist%'
    AND tablename LIKE '%calc%' OR tablename LIKE '%value%' OR tablename LIKE '%data%'
    ORDER BY schemaname, tablename
""")
tables = cur.fetchall()
for schema, table in tables:
    print(f"   {schema}.{table}")

# 2. Check historian_calc_values for recent data
print("\n2. Checking historian_calc_values for TODAY's data...")
try:
    cur.execute("""
        SELECT 
            DATE(timestamp AT TIME ZONE 'UTC') as date,
            COUNT(*) as records,
            COUNT(DISTINCT tag_id) as unique_tags,
            MIN(timestamp) as first_record,
            MAX(timestamp) as last_record
        FROM historian_raw.historian_calc_values
        WHERE timestamp >= NOW() - INTERVAL '48 hours'
        GROUP BY DATE(timestamp AT TIME ZONE 'UTC')
        ORDER BY date DESC
    """)
    rows = cur.fetchall()
    if rows:
        for row in rows:
            print(f"   {row[0]}: {row[1]:,} records, {row[2]} tags")
            print(f"      First: {row[3]}, Last: {row[4]}")
    else:
        print("   ❌ NO RECENT DATA!")
except Exception as e:
    print(f"   Error: {e}")

# 3. Check specific tag values
print("\n3. Sample tag values from historian_calc_values:")
try:
    cur.execute("""
        SELECT tag_id, timestamp, value
        FROM historian_raw.historian_calc_values
        WHERE timestamp >= NOW() - INTERVAL '2 hours'
        ORDER BY timestamp DESC
        LIMIT 10
    """)
    rows = cur.fetchall()
    if rows:
        for row in rows:
            print(f"   {row[1]}: {row[0]} = {row[2]}")
    else:
        print("   ❌ NO DATA in last 2 hours!")
except Exception as e:
    print(f"   Error: {e}")

# 4. Check if C# backend is writing data
print("\n4. Checking writer_checkpoints (C# backend status):")
try:
    cur.execute("""
        SELECT worker_name, last_checkpoint_at, total_writes
        FROM historian_admin.writer_checkpoints
        ORDER BY last_checkpoint_at DESC
    """)
    rows = cur.fetchall()
    if rows:
        for row in rows:
            print(f"   {row[0]}: Last write at {row[1]} ({row[2]} total)")
    else:
        print("   ⚠️  No writer checkpoints found")
except Exception as e:
    print(f"   Error: {e}")

# 5. Check if view aggregation is working
print("\n5. Testing v_daily_hourly_agg with REAL data:")
now = datetime.now()
today = now.date()
current_hour = now.hour
try:
    cur.execute("""
        SELECT 
            tag_id,
            local_date,
            local_hour,
            avg_val,
            sample_count
        FROM historian_raw.v_daily_hourly_agg
        WHERE local_date = %s
        AND local_hour = %s
        LIMIT 5
    """, (today, current_hour))
    rows = cur.fetchall()
    if rows:
        print(f"   Data for TODAY ({today}) hour {current_hour}:")
        for row in rows:
            print(f"      {row[0]}: avg={row[3]}, samples={row[4]}")
    else:
        print(f"   ⚠️  No aggregated data for TODAY hour {current_hour}")
        print(f"   Trying yesterday...")
        yesterday = today - timedelta(days=1)
        cur.execute("""
            SELECT tag_id, local_date, local_hour, avg_val, sample_count
            FROM historian_raw.v_daily_hourly_agg
            WHERE local_date = %s
            ORDER BY local_hour DESC
            LIMIT 5
        """, (yesterday,))
        rows = cur.fetchall()
        if rows:
            print(f"   Data for YESTERDAY ({yesterday}):")
            for row in rows:
                print(f"      {row[0]} hour {row[2]}: avg={row[3]}, samples={row[4]}")
        else:
            print("   ❌ NO AGGREGATED DATA AT ALL!")
except Exception as e:
    print(f"   Error: {e}")

cur.close()
conn.close()

print("\n" + "="*60)
print("DIAGNOSIS:")
print("="*60)
print("If you see:")
print("  ✓ Recent data in historian_calc_values → System IS collecting")
print("  ❌ NO recent data → C# backend NOT running or NOT connected to PLC")
print("  ✓ Writer checkpoints updated → Backend is writing to DB")
print("  ❌ No writer checkpoints → Backend never started writing")
print("\nIf data exists but values are 0:")
print("  → PLC tags are configured but returning zero values")
print("  → Check OPC connection to actual PLC hardware")
print("="*60 + "\n")
