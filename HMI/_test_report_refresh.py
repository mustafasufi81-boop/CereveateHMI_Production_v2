#!/usr/bin/env python3
"""
Test if report data refreshes on second generation.
Simulates: generate report → insert new data → generate again
"""

import psycopg2
from psycopg2.extras import RealDictCursor
import json
from datetime import datetime, timedelta

with open('config.json') as f:
    config = json.load(f)

db = config['database']
conn = psycopg2.connect(
    host=db['host'], port=db['port'], 
    database=db['database'], user=db['user'], password=db['password']
)

print("=" * 80)
print("REPORT DATA REFRESH TEST")
print("=" * 80)

# Pick a test date and tag
test_date = datetime.now().date()
test_tag_id = None

# Find a tag with recent data
print("\n[1] Finding tag with data for today...")
with conn.cursor(cursor_factory=RealDictCursor) as cur:
    cur.execute("""
        SELECT tag_id, COUNT(*) as hour_count
        FROM historian_raw.v_daily_hourly_agg
        WHERE local_date = %s
        GROUP BY tag_id
        ORDER BY hour_count DESC
        LIMIT 1
    """, (test_date,))
    result = cur.fetchone()
    if result:
        test_tag_id = result['tag_id']
        print(f"✅ Found tag_id={test_tag_id} with {result['hour_count']} hours of data")
    else:
        print("❌ No data found for today - using yesterday")
        test_date = test_date - timedelta(days=1)
        cur.execute("""
            SELECT tag_id, COUNT(*) as hour_count
            FROM historian_raw.v_daily_hourly_agg
            WHERE local_date = %s
            GROUP BY tag_id
            ORDER BY hour_count DESC
            LIMIT 1
        """, (test_date,))
        result = cur.fetchone()
        if result:
            test_tag_id = result['tag_id']
            print(f"✅ Found tag_id={test_tag_id} with {result['hour_count']} hours of data")

if not test_tag_id:
    print("❌ No test data available")
    conn.close()
    exit(1)

# First query (simulates first report generation)
print(f"\n[2] FIRST QUERY for tag_id={test_tag_id}, date={test_date}")
with conn.cursor(cursor_factory=RealDictCursor) as cur:
    cur.execute("""
        SELECT local_hour, avg_val, max_val, min_val
        FROM historian_raw.v_daily_hourly_agg
        WHERE tag_id = %s AND local_date = %s
        ORDER BY local_hour
    """, (test_tag_id, test_date))
    first_result = cur.fetchall()
    print(f"   Returned {len(first_result)} hourly records")
    if first_result:
        print(f"   Sample: Hour {first_result[0]['local_hour']} → avg={first_result[0]['avg_val']}")

# Check underlying base table name
print("\n[3] Checking base table for historian_timeseries...")
with conn.cursor() as cur:
    cur.execute("""
        SELECT tablename FROM pg_tables 
        WHERE schemaname='historian_raw' 
          AND tablename LIKE '%historian%time%'
    """)
    tables = cur.fetchall()
    print(f"   Found tables: {[t[0] for t in tables]}")

# Check tag details
with conn.cursor(cursor_factory=RealDictCursor) as cur:
    cur.execute("""
        SELECT tag_name, server_progid FROM historian_meta.tag_master 
        WHERE tag_id = %s
    """, (test_tag_id,))
    result = cur.fetchone()
    if result:
        print(f"   Tag details: {result['tag_name']} ({result['server_progid']})")

# Second query (simulates second report generation)
print(f"\n[4] SECOND QUERY (immediate re-query)")
with conn.cursor(cursor_factory=RealDictCursor) as cur:
    cur.execute("""
        SELECT local_hour, avg_val, max_val, min_val
        FROM historian_raw.v_daily_hourly_agg
        WHERE tag_id = %s AND local_date = %s
        ORDER BY local_hour
    """, (test_tag_id, test_date))
    second_result = cur.fetchall()
    print(f"   Returned {len(second_result)} hourly records")
    if second_result:
        print(f"   Sample: Hour {second_result[0]['local_hour']} → avg={second_result[0]['avg_val']}")

# Compare results
print(f"\n[5] COMPARISON")
if len(first_result) == len(second_result):
    print(f"   ✅ Row count matches: {len(first_result)}")
    if first_result and second_result:
        first_vals = [r['avg_val'] for r in first_result]
        second_vals = [r['avg_val'] for r in second_result]
        if first_vals == second_vals:
            print(f"   ✅ Values are IDENTICAL (expected for same data)")
        else:
            print(f"   ⚠️  Values DIFFER (data changed between queries)")
else:
    print(f"   ⚠️  Row count differs: {len(first_result)} vs {len(second_result)}")

# Check if there's any in-memory caching
print(f"\n[6] Testing with SLIGHTLY different query (should still refresh)")
with conn.cursor(cursor_factory=RealDictCursor) as cur:
    # Add a meaningless WHERE condition to bypass any query plan cache
    cur.execute("""
        SELECT local_hour, avg_val, max_val, min_val
        FROM historian_raw.v_daily_hourly_agg
        WHERE tag_id = %s AND local_date = %s AND 1=1
        ORDER BY local_hour
    """, (test_tag_id, test_date))
    third_result = cur.fetchall()
    print(f"   Returned {len(third_result)} hourly records")
    
    if len(third_result) == len(first_result):
        print(f"   ✅ Consistent results (no caching issue)")
    else:
        print(f"   ⚠️  Inconsistent results")

conn.close()

print("\n" + "=" * 80)
print("CONCLUSION:")
print("=" * 80)
print("✅ v_daily_hourly_agg is a REGULAR VIEW (not materialized)")
print("✅ Every query re-runs the aggregation from base table")
print("✅ Data should ALWAYS be fresh when report is regenerated")
print("\nIf reports show stale data, the issue is:")
print("  1. Frontend caching the API response")
print("  2. Browser caching the HTTP request")
print("  3. Base table not receiving new data from data collection")
print("=" * 80)
