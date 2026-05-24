#!/usr/bin/env python3
"""Check what PLC tags have historical data"""
import json
import psycopg2
from psycopg2.extras import RealDictCursor

with open('config.json', 'r') as f:
    config = json.load(f)

db = config['database']
conn = psycopg2.connect(
    host=db['host'], port=db['port'], database=db['database'],
    user=db['user'], password=db['password'], cursor_factory=RealDictCursor
)

print("=" * 70)
print("🔍 Checking PLC Tags Historical Data")
print("=" * 70)

with conn.cursor() as cur:
    # Check enabled tags in tag_master
    print("\n📋 Enabled tags in tag_master (PLC-like names):")
    cur.execute("""
        SELECT tag_id, tag_name, enabled 
        FROM historian_meta.tag_master 
        WHERE enabled = true 
        AND (tag_id NOT LIKE 'Random%' AND tag_id NOT LIKE 'Saw%' 
             AND tag_id NOT LIKE 'Square%' AND tag_id NOT LIKE 'Triangle%')
        ORDER BY tag_id
    """)
    plc_tags = cur.fetchall()
    for t in plc_tags:
        print(f"  - {t['tag_id']}")
    
    print(f"\n   Total PLC-like enabled tags: {len(plc_tags)}")
    
    # Check how much data each PLC tag has
    print("\n📊 Historical data count per PLC tag:")
    plc_tag_ids = [t['tag_id'] for t in plc_tags]
    
    if plc_tag_ids:
        cur.execute("""
            SELECT tag_id, COUNT(*) as cnt, MIN(time) as oldest, MAX(time) as newest
            FROM historian_raw.historian_timeseries
            WHERE tag_id = ANY(%s)
            GROUP BY tag_id
            ORDER BY cnt DESC
        """, (plc_tag_ids,))
        
        data_counts = cur.fetchall()
        
        if data_counts:
            for d in data_counts:
                print(f"  {d['tag_id']}: {d['cnt']} points ({d['oldest']} to {d['newest']})")
        else:
            print("  ❌ NO HISTORICAL DATA for any PLC tags!")
            
        # Check which tags have NO data at all
        tags_with_data = {d['tag_id'] for d in data_counts}
        tags_without_data = set(plc_tag_ids) - tags_with_data
        
        if tags_without_data:
            print(f"\n⚠️ Tags with NO historical data ({len(tags_without_data)}):")
            for t in sorted(tags_without_data):
                print(f"  - {t}")
    
    # Compare with OPC tags
    print("\n📊 OPC tags data count (for comparison):")
    cur.execute("""
        SELECT tag_id, COUNT(*) as cnt
        FROM historian_raw.historian_timeseries
        WHERE tag_id LIKE 'Random%' OR tag_id LIKE 'Saw%'
        GROUP BY tag_id
        ORDER BY cnt DESC
        LIMIT 5
    """)
    opc_data = cur.fetchall()
    for d in opc_data:
        print(f"  {d['tag_id']}: {d['cnt']} points")

conn.close()
print("\n" + "=" * 70)
