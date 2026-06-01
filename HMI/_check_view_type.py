#!/usr/bin/env python3
"""Check if v_daily_hourly_agg is a materialized view or regular view."""

import psycopg2
import json

with open('config.json') as f:
    config = json.load(f)

db = config['database']
conn = psycopg2.connect(
    host=db['host'], port=db['port'], 
    database=db['database'], user=db['user'], password=db['password']
)

print("=" * 80)
print("VIEW TYPE CHECK: v_daily_hourly_agg")
print("=" * 80)

with conn.cursor() as cur:
    # Check if it's a materialized view
    cur.execute("""
        SELECT schemaname, matviewname, definition 
        FROM pg_matviews 
        WHERE schemaname='historian_raw' AND matviewname='v_daily_hourly_agg'
    """)
    matview = cur.fetchone()
    
    if matview:
        print("❌ MATERIALIZED VIEW (CACHED - needs REFRESH)")
        print(f"   Schema: {matview[0]}")
        print(f"   Name: {matview[1]}")
        print(f"\n   Definition:")
        print(f"   {matview[2][:200]}...")
        
        # Check when last refreshed
        cur.execute("""
            SELECT last_refresh 
            FROM pg_stat_user_tables 
            WHERE schemaname='historian_raw' AND relname='v_daily_hourly_agg'
        """)
        stats = cur.fetchone()
        if stats:
            print(f"\n   Last stats update: {stats[0]}")
    else:
        # Check if it's a regular view
        cur.execute("""
            SELECT schemaname, viewname, definition 
            FROM pg_views 
            WHERE schemaname='historian_raw' AND viewname='v_daily_hourly_agg'
        """)
        view = cur.fetchone()
        
        if view:
            print("✅ REGULAR VIEW (ALWAYS FRESH - queries base table)")
            print(f"   Schema: {view[0]}")
            print(f"   Name: {view[1]}")
            print(f"\n   Definition:")
            # Print first 500 chars of definition
            defn = view[2]
            print(f"   {defn[:500]}...")
        else:
            print("❌ NOT FOUND!")

print("\n" + "=" * 80)
print("CHECKING DATA FRESHNESS")
print("=" * 80)

# Check latest data timestamps
with conn.cursor() as cur:
    cur.execute("""
        SELECT 
            MAX(local_date) as latest_date,
            COUNT(DISTINCT tag_id) as tag_count,
            COUNT(*) as total_rows
        FROM historian_raw.v_daily_hourly_agg
    """)
    stats = cur.fetchone()
    print(f"\n✅ Latest data date: {stats[0]}")
    print(f"✅ Distinct tags: {stats[1]}")
    print(f"✅ Total hourly records: {stats[2]}")

# Check if historian_calc_values has recent data
with conn.cursor() as cur:
    cur.execute("""
        SELECT 
            MAX(time) as latest_time,
            COUNT(*) as total_rows
        FROM historian_raw.historian_calc_values
        WHERE time >= NOW() - INTERVAL '1 hour'
    """)
    stats = cur.fetchone()
    print(f"\n📊 historian_calc_values (base table):")
    print(f"   Latest timestamp: {stats[0]}")
    print(f"   Rows in last hour: {stats[1]}")

conn.close()

print("\n" + "=" * 80)
print("RESULT:")
print("=" * 80)
print("If this is a REGULAR VIEW → Data is always fresh ✅")
print("If this is a MATERIALIZED VIEW → Needs REFRESH to update ❌")
print("=" * 80)
