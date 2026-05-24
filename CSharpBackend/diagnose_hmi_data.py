"""
HMI Data Loss Diagnostic Script
Checks database writes, intervals, and data flow
"""

import psycopg2
from datetime import datetime, timedelta
import time

# Database connection
conn = psycopg2.connect(
    host="localhost",
    database="Cereveate",
    user="cereveate",
    password="cereveate@222"
)

print("=" * 80)
print("HMI DATA LOSS DIAGNOSTIC")
print("=" * 80)

# 1. Check if data is being written at all
print("\n1. CHECKING RECENT DATA WRITES (Last 5 minutes)")
print("-" * 80)
cur = conn.cursor()
cur.execute("""
    SELECT tag_id, COUNT(*) as count, 
           MAX(time) as latest_time,
           EXTRACT(EPOCH FROM (MAX(time) - MIN(time)))::int as time_span_sec
    FROM historian_raw.historian_timeseries
    WHERE time > NOW() - INTERVAL '5 minutes'
    GROUP BY tag_id
    ORDER BY latest_time DESC
    LIMIT 10
""")

rows = cur.fetchall()
if rows:
    print(f"✅ Found {len(rows)} tags with recent data:")
    for tag_id, count, latest_time, span in rows:
        age_sec = (datetime.now().astimezone() - latest_time).total_seconds()
        print(f"  {tag_id:30s} | {count:4d} samples | Latest: {age_sec:5.1f}s ago | Span: {span}s")
else:
    print("❌ NO DATA in last 5 minutes! Database writes stopped!")

# 2. Check Saw-toothed Waves.Int2 specifically (500ms test tag)
print("\n2. SAW-TOOTHED WAVES.INT2 ANALYSIS (500ms test tag)")
print("-" * 80)
cur.execute("""
    SELECT time, value_num
    FROM historian_raw.historian_timeseries
    WHERE tag_id = 'Saw-toothed Waves.Int2'
      AND time > NOW() - INTERVAL '30 seconds'
    ORDER BY time DESC
    LIMIT 20
""")

rows = cur.fetchall()
if rows:
    print(f"✅ Found {len(rows)} samples in last 30 seconds:")
    intervals = []
    for i, (ts, val) in enumerate(rows):
        if i > 0:
            interval_ms = (prev_ts - ts).total_seconds() * 1000
            intervals.append(interval_ms)
            print(f"  {ts.strftime('%H:%M:%S.%f')[:-3]} | Value: {val:6.0f} | Interval: {interval_ms:6.0f}ms")
        else:
            print(f"  {ts.strftime('%H:%M:%S.%f')[:-3]} | Value: {val:6.0f} | (latest)")
        prev_ts = ts
    
    if intervals:
        avg_interval = sum(intervals) / len(intervals)
        print(f"\n  Average interval: {avg_interval:.0f}ms")
        print(f"  Expected: 500ms | Actual: {avg_interval:.0f}ms | {'✅ GOOD' if abs(avg_interval - 500) < 100 else '❌ WRONG'}")
else:
    print("❌ NO DATA for Saw-toothed Waves.Int2 in last 30 seconds!")

# 3. Check tag master configuration
print("\n3. TAG MASTER CONFIGURATION")
print("-" * 80)
cur.execute("""
    SELECT tag_id, db_logging_interval_ms, deadband_value, enabled
    FROM historian_meta.tag_master
    WHERE tag_id = 'Saw-toothed Waves.Int2'
""")

row = cur.fetchone()
if row:
    tag_id, interval, deadband, enabled = row
    print(f"  Tag: {tag_id}")
    print(f"  Interval: {interval}ms")
    print(f"  Deadband: {deadband}")
    print(f"  Enabled: {enabled}")
    print(f"  Status: {'✅ ENABLED' if enabled else '❌ DISABLED'}")
else:
    print("❌ Tag not found in tag_master!")

# 4. Check data gaps (potential data loss)
print("\n4. CHECKING FOR DATA GAPS (>2 seconds)")
print("-" * 80)
cur.execute("""
    WITH time_diffs AS (
        SELECT 
            tag_id,
            time,
            LAG(time) OVER (PARTITION BY tag_id ORDER BY time) as prev_time,
            EXTRACT(EPOCH FROM (time - LAG(time) OVER (PARTITION BY tag_id ORDER BY time)))::int as gap_sec
        FROM historian_raw.historian_timeseries
        WHERE time > NOW() - INTERVAL '5 minutes'
    )
    SELECT tag_id, time, prev_time, gap_sec
    FROM time_diffs
    WHERE gap_sec > 2
    ORDER BY time DESC
    LIMIT 10
""")

rows = cur.fetchall()
if rows:
    print(f"⚠️  Found {len(rows)} gaps > 2 seconds:")
    for tag_id, ts, prev_ts, gap in rows:
        print(f"  {tag_id:30s} | Gap: {gap:4d}s | At: {ts.strftime('%H:%M:%S')}")
else:
    print("✅ No significant gaps found")

# 5. Check OPC backend status
print("\n5. OPC BACKEND STATUS")
print("-" * 80)
import socket
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
result = sock.connect_ex(('localhost', 5001))
sock.close()
if result == 0:
    print("✅ OPC backend is RUNNING on port 5001")
else:
    print("❌ OPC backend is NOT RUNNING on port 5001")

# 6. Real-time monitoring for 10 seconds
print("\n6. REAL-TIME MONITORING (10 seconds)")
print("-" * 80)
print("Watching for new data arrivals...")

for i in range(10):
    cur.execute("""
        SELECT tag_id, time, value_num
        FROM historian_raw.historian_timeseries
        WHERE time > NOW() - INTERVAL '1 second'
        ORDER BY time DESC
        LIMIT 5
    """)
    
    rows = cur.fetchall()
    if rows:
        print(f"[{i+1:2d}s] ✅ {len(rows)} samples in last second:")
        for tag_id, ts, val in rows[:3]:
            print(f"      {tag_id:30s} @ {ts.strftime('%H:%M:%S.%f')[:-3]}")
    else:
        print(f"[{i+1:2d}s] ❌ No data in last second")
    
    time.sleep(1)

cur.close()
conn.close()

print("\n" + "=" * 80)
print("DIAGNOSTIC COMPLETE")
print("=" * 80)
