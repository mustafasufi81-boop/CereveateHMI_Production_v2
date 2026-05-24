#!/usr/bin/env python3
"""
Show exact parameters being passed to the query
"""
import psycopg2
import json
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta

# Load config
with open('config.json') as f:
    config = json.load(f)

# Calculate the exact same parameters as the service
end_time = datetime.now()
start_time = end_time - timedelta(hours=1)
tag_ids = ['Saw-toothed Waves.Int1']
max_points = 100

# Calculate sampling interval (same logic as service)
total_seconds = (end_time - start_time).total_seconds()
sampling_interval = max(1, int(total_seconds / max_points))
interval_str = f"{sampling_interval} seconds"

print(f"🔍 EXACT PARAMETERS BEING USED:")
print(f"   start_time: {start_time}")
print(f"   end_time: {end_time}")
print(f"   tag_ids: {tag_ids}")
print(f"   interval_str: {interval_str}")
print(f"   total_seconds: {total_seconds}")
print(f"   sampling_interval: {sampling_interval}")

# Connect and run the exact query
try:
    conn = psycopg2.connect(**config['database'])
    
    with conn.cursor(cursor_factory=RealDictCursor) as cursor:
        print(f"\n🗣️  RUNNING EXACT QUERY:")
        query = """
            SELECT 
                tag_id,
                time_bucket(%s::interval, time) AS timestamp,
                AVG(value_num) as value,
                MAX(quality) as quality
            FROM historian_raw.historian_timeseries
            WHERE tag_id = ANY(%s) 
              AND time >= %s 
              AND time <= %s
            GROUP BY tag_id, time_bucket(%s::interval, time)
            ORDER BY tag_id, timestamp
        """
        
        params = (interval_str, tag_ids, start_time, end_time, interval_str)
        
        print(f"Query: {query}")
        print(f"Params: {params}")
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        print(f"\n✅ QUERY RESULT: {len(rows)} rows")
        for i, row in enumerate(rows[:3]):  # Show first 3
            print(f"   Row {i+1}: {dict(row)}")
            
        if len(rows) == 0:
            print("\n❌ NO ROWS RETURNED - Let's check why...")
            
            # Check if data exists at all for this tag
            cursor.execute(
                "SELECT COUNT(*) as count FROM historian_raw.historian_timeseries WHERE tag_id = %s",
                (tag_ids[0],)
            )
            total_count = cursor.fetchone()['count']
            print(f"   Total rows for tag '{tag_ids[0]}': {total_count}")
            
            # Check if data exists in time range
            cursor.execute(
                "SELECT COUNT(*) as count FROM historian_raw.historian_timeseries WHERE tag_id = %s AND time >= %s AND time <= %s",
                (tag_ids[0], start_time, end_time)
            )
            range_count = cursor.fetchone()['count']
            print(f"   Rows in time range: {range_count}")
    
    conn.close()
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()