#!/usr/bin/env python3
"""Check tags mapped in historian database"""
import psycopg2

# Correct credentials from appsettings.json
conn = psycopg2.connect(
    host='localhost',
    port=5432,
    database='Cereveate',
    user='cereveate',
    password='cereveate@222'
)

cur = conn.cursor()

# Get all mapped tags
cur.execute("""
    SELECT tag_id, tag_name, enabled, data_type, eng_unit, plant, area, equipment
    FROM historian_meta.tag_master 
    ORDER BY tag_id
""")

rows = cur.fetchall()

print(f"\n{'='*80}")
print(f"DATABASE MAPPED TAGS: {len(rows)} total")
print(f"{'='*80}\n")

for i, row in enumerate(rows, 1):
    tag_id, tag_name, enabled, data_type, eng_unit, plant, area, equipment = row
    status = "✅ ENABLED" if enabled else "❌ DISABLED"
    print(f"{i:3}. {status} | {tag_id:40} | {tag_name}")
    
print(f"\n{'='*80}")
print(f"Summary: {sum(1 for r in rows if r[2])} enabled, {sum(1 for r in rows if not r[2])} disabled")
print(f"{'='*80}\n")

cur.close()
conn.close()
