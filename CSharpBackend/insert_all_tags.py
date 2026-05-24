import psycopg2
import json

with open('tags_to_insert.json') as f:
    tags = json.load(f)

conn = psycopg2.connect(host='localhost', port=5432, dbname='Automation_DB', user='cereveate', password='cereveate@222')
cur = conn.cursor()

print(f"Total tags in JSON: {len(tags)}")

inserted = 0
skipped = 0
errors = []

for t in tags:
    try:
        cur.execute("""
            INSERT INTO historian_meta.tag_master (
                tag_id, tag_name, description, plant, area, equipment,
                sub_equipment, components, data_type, eng_unit,
                alarm_enabled, alarm_h_limit, alarm_hh_limit, alarm_l_limit, alarm_ll_limit,
                alarm_priority, alarm_deadband, equipment_criticality,
                db_logging_interval_ms, logging_interval_ms,
                deadband_enabled, deadband_value, enabled, db_table_name,
                server_progid, plc_ip_address, plc_port, plc_protocol,
                plc_path, plc_type, plc_timeout_ms, plc_polling_interval_ms,
                include_in_report, report_flag, created_by
            ) VALUES (
                %(tag_id)s, %(tag_name)s, %(description)s, %(plant)s, %(area)s, %(equipment)s,
                %(sub_equipment)s, %(components)s, %(data_type)s, %(eng_unit)s,
                %(alarm_enabled)s, %(alarm_h_limit)s, %(alarm_hh_limit)s, %(alarm_l_limit)s, %(alarm_ll_limit)s,
                %(alarm_priority)s, %(alarm_deadband)s, %(equipment_criticality)s,
                %(db_logging_interval_ms)s, %(logging_interval_ms)s,
                %(deadband_enabled)s, %(deadband_value)s, %(enabled)s, %(db_table_name)s,
                %(server_progid)s, %(plc_ip_address)s, %(plc_port)s, %(plc_protocol)s,
                %(plc_path)s, %(plc_type)s, %(plc_timeout_ms)s, %(plc_polling_interval_ms)s,
                %(include_in_report)s, %(report_flag)s, %(created_by)s
            )
            ON CONFLICT (tag_id) DO NOTHING
        """, t)
        if cur.rowcount == 1:
            inserted += 1
        else:
            skipped += 1
            print(f"  SKIPPED (already exists): {t['tag_id']}")
    except Exception as e:
        errors.append((t['tag_id'], str(e)))
        conn.rollback()
        print(f"  ERROR {t['tag_id']}: {e}")
        continue

conn.commit()

print(f"\n--- INSERT SUMMARY ---")
print(f"  Inserted : {inserted}")
print(f"  Skipped  : {skipped} (already existed)")
print(f"  Errors   : {len(errors)}")
if errors:
    for tag_id, err in errors:
        print(f"    {tag_id}: {err}")

# Verification: count FTP-1/POTLINE tags
cur.execute("SELECT COUNT(*) FROM historian_meta.tag_master WHERE plant='FTP-1' AND area='POTLINE'")
total_potline = cur.fetchone()[0]
print(f"\n--- VERIFICATION ---")
print(f"  Total FTP-1/POTLINE tags in DB: {total_potline}")

# Check mapping_version all = 1 for newly inserted
cur.execute("""
    SELECT mapping_version, COUNT(*) 
    FROM historian_meta.tag_master 
    WHERE plant='FTP-1' AND area='POTLINE'
    GROUP BY mapping_version ORDER BY mapping_version
""")
print("  mapping_version distribution:")
for row in cur.fetchall():
    print(f"    version={row[0]}  count={row[1]}")

# Check all have config_updated_at set
cur.execute("""
    SELECT COUNT(*) FROM historian_meta.tag_master 
    WHERE plant='FTP-1' AND area='POTLINE' AND config_updated_at IS NULL
""")
null_ts = cur.fetchone()[0]
print(f"  Tags with NULL config_updated_at: {null_ts} (should be 0)")

# Check all enabled
cur.execute("""
    SELECT COUNT(*) FROM historian_meta.tag_master 
    WHERE plant='FTP-1' AND area='POTLINE' AND enabled=TRUE
""")
enabled_count = cur.fetchone()[0]
print(f"  Enabled tags: {enabled_count}")

# Show sample of inserted tags
cur.execute("""
    SELECT tag_id, tag_name, data_type, eng_unit, alarm_enabled, mapping_version, created_at
    FROM historian_meta.tag_master 
    WHERE plant='FTP-1' AND area='POTLINE'
    ORDER BY created_at DESC
    LIMIT 10
""")
print(f"\n  Last 10 inserted tags:")
print(f"  {'tag_id':<12} {'tag_name':<12} {'dtype':<8} {'unit':<6} {'alarm':<6} {'ver':<4} {'created_at'}")
print(f"  {'-'*80}")
for r in cur.fetchall():
    print(f"  {r[0]:<12} {r[1]:<12} {r[2]:<8} {str(r[3]):<6} {str(r[4]):<6} {str(r[5]):<4} {r[6]}")

conn.close()
print("\nDONE.")
