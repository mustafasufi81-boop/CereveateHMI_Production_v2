"""
Simple Query Test - 5 Second Intervals for Random.UInt1
Uses the EXACT query from the HMI application
"""
import psycopg2
from datetime import datetime, timedelta

# Database connection (from HMI config.json)
conn = psycopg2.connect(
    host='localhost',
    port=5432,
    database='Cereveate',
    user='cereveate',
    password='cereveate@222'
)

cursor = conn.cursor()

# Test parameters
tag_id = 'Random.UInt1'
hours = 6
sampling_interval = 5  # 5 SECONDS

# Calculate time range
end_time = datetime.now()
start_time = end_time - timedelta(hours=hours)

print(f"Testing Query for: {tag_id}")
print(f"Time Range: {start_time.strftime('%Y-%m-%d %H:%M:%S')} to {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
print(f"Sampling Interval: {sampling_interval} seconds")
print("="*80)

# EXACT query from historical_data.py (FIXED to avoid duplicates)
query = """
    SELECT DISTINCT ON (time_bucket(%s::interval, time))
        time as timestamp,
        value_num as value,
        quality
    FROM historian_raw.historian_timeseries
    WHERE tag_id = %s
    AND time BETWEEN %s AND %s
    AND EXTRACT(EPOCH FROM time)::bigint %% %s = 0
    ORDER BY time_bucket(%s::interval, time), time
"""

print("\nExecuting query...")
interval_str = f"{sampling_interval} seconds"
cursor.execute(query, (interval_str, tag_id, start_time, end_time, sampling_interval, interval_str))
rows = cursor.fetchall()

print(f"\n✅ Query returned {len(rows)} records\n")

if len(rows) == 0:
    print("⚠️ No data found! Checking if ANY data exists...")
    cursor.execute("""
        SELECT COUNT(*), MIN(time), MAX(time)
        FROM historian_raw.historian_timeseries
        WHERE tag_id = %s AND time BETWEEN %s AND %s
    """, (tag_id, start_time, end_time))
    count, min_t, max_t = cursor.fetchone()
    print(f"Total records (any time): {count}")
    if count > 0:
        print(f"First: {min_t}, Last: {max_t}")
else:
    # Show first 20 records
    print(f"{'TIMESTAMP':<25} {'VALUE':<15} {'QUALITY':<10} {'INTERVAL'}")
    print("-"*70)
    
    prev_time = None
    for i, (timestamp, value, quality) in enumerate(rows[:20]):
        interval = ""
        if prev_time:
            diff = (timestamp - prev_time).total_seconds()
            interval = f"{diff:.0f}s"
        print(f"{timestamp.strftime('%Y-%m-%d %H:%M:%S'):<25} {value:<15.2f} {quality:<10} {interval}")
        prev_time = timestamp
    
    if len(rows) > 20:
        print(f"\n... ({len(rows) - 20} more records)")
    
    # Statistics
    if len(rows) > 1:
        total_time = (rows[-1][0] - rows[0][0]).total_seconds()
        avg_interval = total_time / (len(rows) - 1)
        print(f"\n📊 Statistics:")
        print(f"   Total records: {len(rows)}")
        print(f"   Time span: {total_time/3600:.2f} hours")
        print(f"   Average interval: {avg_interval:.1f} seconds")
        print(f"   Expected interval: {sampling_interval} seconds")

cursor.close()
conn.close()
print("\n✅ Test complete!")
