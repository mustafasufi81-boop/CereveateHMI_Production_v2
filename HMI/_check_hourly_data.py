import json, psycopg2
from datetime import date, timedelta

with open('config.json', 'r') as f:
    config = json.load(f)

db = config['database']
conn = psycopg2.connect(host=db['host'], port=db['port'], database=db['database'], user=db['user'], password=db['password'])
cur = conn.cursor()

test_date = date.today() - timedelta(days=1)
test_tag = 'Bucket Brigade.Real4'

print(f"\n🔍 CHECKING HOURLY AGGREGATION DATA")
print(f"Date: {test_date}")
print(f"Tag: {test_tag}\n")

# Check v_daily_hourly_agg
print("1. v_daily_hourly_agg view:")
cur.execute("""
    SELECT local_date, local_hour, avg_val, max_val, min_val 
    FROM historian_raw.v_daily_hourly_agg 
    WHERE tag_id = %s AND local_date = %s 
    ORDER BY local_hour 
    LIMIT 5
""", (test_tag, test_date))
rows = cur.fetchall()
if rows:
    for row in rows:
        print(f"   Hour {row[1]}: avg={row[2]}, max={row[3]}, min={row[4]}")
else:
    print("   ❌ NO DATA in v_daily_hourly_agg")

# Check raw historian data
print("\n2. historian_raw.historian_latest_value:")
cur.execute("""
    SELECT tag_id, value, quality, last_updated
    FROM historian_raw.historian_latest_value 
    WHERE tag_id = %s
""", (test_tag,))
row = cur.fetchone()
if row:
    print(f"   Tag: {row[0]}")
    print(f"   Value: {row[1]}")
    print(f"   Quality: {row[2]}")
    print(f"   Updated: {row[3]}")
else:
    print("   ❌ NO DATA in historian_latest_value")

# Check if calc values table exists
print("\n3. historian_raw.historian_calc_values:")
try:
    cur.execute("""
        SELECT tag_id, timestamp, value 
        FROM historian_raw.historian_calc_values 
        WHERE tag_id = %s 
        AND timestamp >= %s::date 
        AND timestamp < %s::date + interval '1 day'
        ORDER BY timestamp 
        LIMIT 5
    """, (test_tag, test_date, test_date))
    rows = cur.fetchall()
    if rows:
        for row in rows:
            print(f"   {row[1]}: {row[2]}")
        cur.execute("""
            SELECT COUNT(*) 
            FROM historian_raw.historian_calc_values 
            WHERE tag_id = %s 
            AND timestamp >= %s::date 
            AND timestamp < %s::date + interval '1 day'
        """, (test_tag, test_date, test_date))
        total = cur.fetchone()[0]
        print(f"   Total records: {total}")
    else:
        print("   ❌ NO DATA for this date")
except Exception as e:
    print(f"   Error: {e}")

# Check view definition
print("\n4. View definition:")
cur.execute("""
    SELECT pg_get_viewdef('historian_raw.v_daily_hourly_agg'::regclass, true)
""")
viewdef = cur.fetchone()[0]
print(viewdef[:500] + "...")

cur.close()
conn.close()
print("\n✅ CHECK COMPLETE\n")
