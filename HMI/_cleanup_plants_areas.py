#!/usr/bin/env python3
"""Clean up plants_areas table - remove duplicates and orphan entries."""

import psycopg2
from psycopg2.extras import RealDictCursor
import json

with open('config.json') as f:
    config = json.load(f)

db = config['database']
conn = psycopg2.connect(
    host=db['host'], port=db['port'], 
    database=db['database'], user=db['user'], password=db['password']
)

print("=" * 80)
print("CLEANING UP PLANTS_AREAS TABLE")
print("=" * 80)

# 1. Show current state
print("\n[1] Current plants_areas entries:")
with conn.cursor(cursor_factory=RealDictCursor) as cur:
    cur.execute("""
        SELECT pa.id, pa.server_progid, pa.plant, pa.area, pa.plant_code, pa.is_active,
               (SELECT COUNT(*) FROM historian_meta.tag_master tm 
                WHERE tm.server_progid = pa.server_progid 
                  AND tm.plant = pa.plant 
                  AND tm.area = pa.area 
                  AND tm.enabled = true) as tag_count
        FROM historian_meta.plants_areas pa
        ORDER BY pa.is_active DESC, pa.id
    """)
    entries = cur.fetchall()
    
    for e in entries:
        status = "✅" if e['tag_count'] > 0 else "❌ ORPHAN"
        active_mark = "ACTIVE" if e['is_active'] else "INACTIVE"
        progid = e['server_progid'] or 'NULL'
        plant = e['plant'] or 'NULL'
        area = e['area'] or 'NULL'
        print(f"  ID:{e['id']:3d} {status} [{active_mark:8s}] {progid:30s} / {plant:15s} / {area:15s} [{e['tag_count']} tags]")

# 2. Identify entries to keep (those with tags)
print("\n[2] Identifying valid entries (have tags)...")
with conn.cursor(cursor_factory=RealDictCursor) as cur:
    cur.execute("""
        SELECT DISTINCT pa.id, pa.server_progid, pa.plant, pa.area
        FROM historian_meta.plants_areas pa
        INNER JOIN historian_meta.tag_master tm 
            ON tm.server_progid = pa.server_progid 
            AND tm.plant = pa.plant 
            AND tm.area = pa.area 
            AND tm.enabled = true
        ORDER BY pa.id
    """)
    valid_entries = cur.fetchall()
    
    print(f"  Found {len(valid_entries)} valid entries:")
    for v in valid_entries:
        print(f"    ID:{v['id']} - {v['server_progid']} / {v['plant']} / {v['area']}")

# 3. Check for user assignments on entries we want to delete
print("\n[3] Checking user_area_assignments...")
with conn.cursor(cursor_factory=RealDictCursor) as cur:
    valid_ids = [v['id'] for v in valid_entries]
    cur.execute("""
        SELECT plant_area_id, COUNT(*) as user_count
        FROM historian_meta.user_area_assignments
        WHERE plant_area_id NOT IN %s
        GROUP BY plant_area_id
    """, (tuple(valid_ids),))
    assignments = cur.fetchall()
    
    if assignments:
        print(f"  ⚠️  WARNING: {len(assignments)} orphan entries have user assignments:")
        for a in assignments:
            print(f"    plant_area_id={a['plant_area_id']}: {a['user_count']} users assigned")
        
        # Delete these assignments first
        print("\n[4] Deleting orphan user assignments...")
        with conn.cursor() as cur:
            cur.execute("""
                DELETE FROM historian_meta.user_area_assignments
                WHERE plant_area_id NOT IN %s
            """, (tuple(valid_ids),))
            deleted = cur.rowcount
            conn.commit()
            print(f"  ✅ Deleted {deleted} orphan user assignments")
    else:
        print("  ✅ No user assignments on orphan entries")

# 4. Handle duplicate (ID:5 vs ID:37 for Rockwel_PLC_001/FTP-1/POTLINE)
print("\n[5] Checking for duplicates...")
with conn.cursor(cursor_factory=RealDictCursor) as cur:
    cur.execute("""
        SELECT server_progid, plant, area, array_agg(id ORDER BY id) as ids, COUNT(*) as count
        FROM historian_meta.plants_areas
        WHERE id IN %s
        GROUP BY server_progid, plant, area
        HAVING COUNT(*) > 1
    """, (tuple(valid_ids),))
    duplicates = cur.fetchall()
    
    if duplicates:
        print(f"  ⚠️  Found {len(duplicates)} duplicate groups:")
        for dup in duplicates:
            print(f"    {dup['server_progid']} / {dup['plant']} / {dup['area']}")
            print(f"      IDs: {dup['ids']} - will keep {dup['ids'][-1]} (newest)")
            
            # Remove older duplicates from valid_ids list
            ids_to_remove = dup['ids'][:-1]  # Keep only the last (newest) ID
            for old_id in ids_to_remove:
                if old_id in valid_ids:
                    valid_ids.remove(old_id)
                    print(f"      Marked ID:{old_id} for deletion")
    else:
        print("  ✅ No duplicates found")

# 5. Delete all entries except valid ones
print("\n[6] Deleting orphan and duplicate entries...")
with conn.cursor() as cur:
    valid_ids_final = [v['id'] for v in valid_entries if v['id'] in valid_ids]
    cur.execute("""
        DELETE FROM historian_meta.plants_areas
        WHERE id NOT IN %s
    """, (tuple(valid_ids_final),))
    deleted = cur.rowcount
    conn.commit()
    print(f"  ✅ Deleted {deleted} entries")

# 6. Show final state
print("\n[7] Final plants_areas state:")
with conn.cursor(cursor_factory=RealDictCursor) as cur:
    cur.execute("""
        SELECT pa.id, pa.server_progid, pa.plant, pa.area, pa.plant_code, pa.is_active,
               (SELECT COUNT(*) FROM historian_meta.tag_master tm 
                WHERE tm.server_progid = pa.server_progid 
                  AND tm.plant = pa.plant 
                  AND tm.area = pa.area 
                  AND tm.enabled = true) as tag_count
        FROM historian_meta.plants_areas pa
        ORDER BY pa.server_progid, pa.plant, pa.area
    """)
    final_entries = cur.fetchall()
    
    print(f"  Total entries: {len(final_entries)}")
    for e in final_entries:
        print(f"    ID:{e['id']:3d} ✅ [{e['tag_count']:3d} tags] {e['server_progid']:30s} / {e['plant']:15s} / {e['area']:15s}")

conn.close()

print("\n" + "=" * 80)
print("CLEANUP COMPLETE")
print("=" * 80)
print("✅ Only entries with actual tags remain in plants_areas")
print("✅ Report dropdown will now show only valid sources")
print("✅ Trigger will keep table in sync when tags are added/removed")
print("=" * 80)
