import psycopg2
import json
from datetime import datetime

# Load config from historian_query_tool_v2.py's config.json
with open('config.json', 'r') as f:
    config = json.load(f)

# Database connection
conn = psycopg2.connect(
    host=config['database']['host'],
    database=config['database']['database'],
    user=config['database']['user'],
    password=config['database']['password'],
    port=config['database']['port']
)

cursor = conn.cursor()

# Check exact records around 6:30 AM for Welding_Current_A
query = """
SELECT 
    time,
    tag_id,
    value_num,
    EXTRACT(EPOCH FROM time) as epoch_seconds,
    EXTRACT(MICROSECONDS FROM time) as total_microseconds,
    EXTRACT(MILLISECONDS FROM time) as milliseconds_from_second
FROM historian_raw.historian_timeseries
WHERE tag_id = 'Welding_Current_A'
    AND time >= '2026-02-09 06:30:00+05:30'
    AND time < '2026-02-09 06:31:00+05:30'
ORDER BY time
LIMIT 100;
"""

cursor.execute(query)
rows = cursor.fetchall()

print("=" * 120)
print(f"WELDING_CURRENT_A RECORDS AT 6:30 AM - Total found: {len(rows)}")
print("=" * 120)

if len(rows) == 0:
    print("\n❌ NO RECORDS FOUND at 6:30 AM")
    print("\nChecking what time range has data...")
    
    cursor.execute("""
        SELECT MIN(time), MAX(time), COUNT(*)
        FROM historian_raw.historian_timeseries
        WHERE tag_id = 'Welding_Current_A'
    """)
    min_time, max_time, total_count = cursor.fetchone()
    print(f"\nWelding_Current_A data range:")
    print(f"  First record: {min_time}")
    print(f"  Last record:  {max_time}")
    print(f"  Total records: {total_count:,}")
else:
    print(f"\n{'Time':<35} | {'Value':<10} | {'Microseconds':<15} | {'Milliseconds':<15}")
    print("-" * 120)
    
    zero_ms_count = 0
    non_zero_ms_count = 0
    
    for row in rows:
        time_val, tag_id, value, epoch, microseconds, milliseconds = row
        
        # Extract just the microsecond part (0-999999)
        microsecond_part = int(microseconds) % 1000000
        millisecond_part = microsecond_part // 1000
        
        if millisecond_part == 0:
            zero_ms_count += 1
            marker = " ❌ .000"
        else:
            non_zero_ms_count += 1
            marker = " ✅"
        
        print(f"{str(time_val):<35} | {value:<10.3f} | {microsecond_part:<15} | {millisecond_part:<15}{marker}")
    
    print("=" * 120)
    print(f"\nSUMMARY:")
    print(f"  Records with .000 milliseconds: {zero_ms_count}")
    print(f"  Records with non-zero milliseconds: {non_zero_ms_count}")
    print(f"  Percentage with .000: {(zero_ms_count/len(rows)*100):.1f}%")
    
    if zero_ms_count == len(rows):
        print("\n⚠️  WARNING: ALL records at 6:30 AM have exactly .000 milliseconds")
        print("   This could indicate:")
        print("   1. Data source only writes at whole-second boundaries")
        print("   2. Millisecond precision lost during data ingestion")
        print("   3. Coincidence (unlikely if all 100 records are .000)")

cursor.close()
conn.close()
