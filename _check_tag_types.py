import psycopg2

c = psycopg2.connect(host='localhost', database='Automation_DB',
                     user='cereveate', password='cereveate@222')
cur = c.cursor()

print("=== ALL distinct data_type values in tag_master (server_progid set, enabled) ===")
cur.execute("""
    SELECT data_type, COUNT(*)
    FROM historian_meta.tag_master
    WHERE server_progid IS NOT NULL AND enabled = true
    GROUP BY data_type ORDER BY 2 DESC
""")
for r in cur.fetchall():
    print(f"  {r[0]!r:12} -> {r[1]}")

print("\n=== The non-'double' tags (string / integer) — full detail ===")
cur.execute("""
    SELECT tag_name, data_type, eng_unit, description, server_progid
    FROM historian_meta.tag_master
    WHERE server_progid IS NOT NULL AND enabled = true
      AND lower(data_type) NOT IN ('double','float')
    ORDER BY data_type, tag_name
""")
for r in cur.fetchall():
    print(f"  {r[0]:18} type={r[1]!r:10} unit={r[2]!r:8} desc={r[3]!r}  plc={r[4]}")

print("\n=== Is there any column holding a PLC-native type (REAL/DINT/BOOL)? ===")
cur.execute("""
    SELECT column_name FROM information_schema.columns
    WHERE table_schema='historian_meta' AND table_name='tag_master'
      AND (column_name ILIKE '%type%')
    ORDER BY column_name
""")
for r in cur.fetchall():
    print(f"  {r[0]}")

c.close()
