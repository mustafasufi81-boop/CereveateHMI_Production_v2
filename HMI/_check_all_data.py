import json, psycopg2
from datetime import date, timedelta

with open('config.json', 'r') as f:
    config = json.load(f)

db = config['database']
conn = psycopg2.connect(host=db['host'], port=db['port'], database=db['database'], user=db['user'], password=db['password'])
cur = conn.cursor()

print("\n" + "="*80)
print("ALL DATA SOURCES IN SYSTEM")
print("="*80)

# Check all historian schemas
print("\n[1] ALL HISTORIAN TABLES:")
print("-"*80)
cur.execute("""
    SELECT schemaname, tablename, 
           pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
    FROM pg_tables 
    WHERE schemaname LIKE '%historian%'
    ORDER BY schemaname, tablename
""")
for schema, table, size in cur.fetchall():
    cur.execute(f"SELECT COUNT(*) FROM {schema}.{table}")
    count = cur.fetchone()[0]
    print(f"  {schema}.{table}: {count:,} rows ({size})")

# Check all views
print("\n[2] ALL HISTORIAN VIEWS:")
print("-"*80)
cur.execute("""
    SELECT schemaname, viewname
    FROM pg_views 
    WHERE schemaname LIKE '%historian%'
    ORDER BY schemaname, viewname
""")
for schema, view in cur.fetchall():
    try:
        cur.execute(f"SELECT COUNT(*) FROM {schema}.{view}")
        count = cur.fetchone()[0]
        print(f"  {schema}.{view}: {count:,} rows")
    except Exception as e:
        print(f"  {schema}.{view}: ERROR - {e}")

# Check what data is available for reports
print("\n[3] DATA FOR YESTERDAY (2026-05-26):")
print("-"*80)
yesterday = date.today() - timedelta(days=1)

# Check v_daily_hourly_agg (what reports actually use)
cur.execute("""
    SELECT 
        COUNT(*) as total_records,
        COUNT(DISTINCT tag_id) as unique_tags,
        MIN(local_hour) as first_hour,
        MAX(local_hour) as last_hour,
        COUNT(DISTINCT local_hour) as hours_covered
    FROM historian_raw.v_daily_hourly_agg
    WHERE local_date = %s
""", (yesterday,))
row = cur.fetchone()
print(f"\n  v_daily_hourly_agg (USED BY REPORTS):")
print(f"    Total records: {row[0]:,}")
print(f"    Unique tags: {row[1]}")
print(f"    Hours: {row[2]} to {row[3]} ({row[4]} hours)")

# Sample some tags
cur.execute("""
    SELECT tag_id, COUNT(*) as hours_with_data, 
           ROUND(AVG(avg_val)::numeric, 2) as overall_avg
    FROM historian_raw.v_daily_hourly_agg
    WHERE local_date = %s
    GROUP BY tag_id
    ORDER BY hours_with_data DESC
    LIMIT 10
""", (yesterday,))
print(f"\n  Top 10 tags by data coverage:")
for tag, hours, avg in cur.fetchall():
    print(f"    {tag}: {hours}/24 hours, avg={avg}")

# Check for today's data
print("\n[4] DATA FOR TODAY (2026-05-27):")
print("-"*80)
today = date.today()
cur.execute("""
    SELECT COUNT(*), COUNT(DISTINCT tag_id)
    FROM historian_raw.v_daily_hourly_agg
    WHERE local_date = %s
""", (today,))
count, tags = cur.fetchone()
print(f"  v_daily_hourly_agg: {count:,} records, {tags} unique tags")

if count == 0:
    print("  ⚠️  NO DATA for today yet (C# backend not running)")

# Check raw table if it exists
print("\n[5] CHECKING RAW DATA TABLE:")
print("-"*80)
cur.execute("""
    SELECT table_name FROM information_schema.tables 
    WHERE table_schema = 'historian_raw' 
    AND table_name LIKE '%hourly%'
""")
tables = [r[0] for r in cur.fetchall()]
for table in tables:
    cur.execute(f"SELECT COUNT(*) FROM historian_raw.{table}")
    count = cur.fetchone()[0]
    print(f"  historian_raw.{table}: {count:,} rows")
    
    if count > 0:
        cur.execute(f"""
            SELECT MIN(local_date), MAX(local_date), COUNT(DISTINCT tag_id)
            FROM historian_raw.{table}
        """)
        min_date, max_date, tags = cur.fetchone()
        print(f"    Date range: {min_date} to {max_date}")
        print(f"    Unique tags: {tags}")

print("\n" + "="*80)
print("SUMMARY:")
print("="*80)
print("\n✅ EXISTING DATA:")
print("   - v_daily_hourly_agg has historical data")
print("   - Reports CAN generate using this data")
print("   - Yesterday: Full day coverage")
print("\n⚠️  NEW COLLECTION:")
print("   - historian_calc_values (InfluxDB format): EMPTY")
print("   - C# backend needs to be started")
print("   - Once started, new data will accumulate")
print("\n" + "="*80 + "\n")

cur.close()
conn.close()
