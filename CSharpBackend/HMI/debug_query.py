#!/usr/bin/env python3
"""
Debug the historical data service query
"""
import sys
sys.path.append('.')

from services.historical_data import HistoricalDataService
import json
import logging
from datetime import datetime, timedelta

# Enable debug logging
logging.basicConfig(level=logging.DEBUG)

# Load config
with open('config.json') as f:
    config = json.load(f)

# Test the service directly with debug
service = HistoricalDataService(config['database'])
if service.connect():
    print('✅ Connected to database')
    
    # Test with exact time range and simple query
    end_time = datetime.now()
    start_time = end_time - timedelta(hours=1)
    
    print(f'🕐 Time range: {start_time} to {end_time}')
    print(f'📊 Testing: Saw-toothed Waves.Int1')
    
    # Test the exact query manually first
    import psycopg2
    from psycopg2.extras import RealDictCursor
    
    try:
        with service._get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                # First test: simple count
                cursor.execute("""
                    SELECT COUNT(*) as count
                    FROM historian_raw.historian_timeseries
                    WHERE tag_id = %s AND time >= %s AND time <= %s
                """, ('Saw-toothed Waves.Int1', start_time, end_time))
                
                count_result = cursor.fetchone()
                print(f'🔍 Raw count query: {count_result["count"]} rows found')
                
                # Second test: the time_bucket query
                interval_str = "60 seconds"
                cursor.execute("""
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
                    LIMIT 3
                """, (interval_str, ['Saw-toothed Waves.Int1'], start_time, end_time, interval_str))
                
                bucket_results = cursor.fetchall()
                print(f'🪣 Time bucket query: {len(bucket_results)} buckets')
                for row in bucket_results:
                    print(f'   {row["tag_id"]}: {row["value"]} at {row["timestamp"]}')
                    
    except Exception as e:
        print(f'❌ Manual query failed: {e}')
        import traceback
        traceback.print_exc()
    
    service.disconnect()
else:
    print('❌ Failed to connect')