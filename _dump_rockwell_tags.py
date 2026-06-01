import psycopg2

c = psycopg2.connect(host='localhost', database='Automation_DB',
                     user='cereveate', password='cereveate@222')
cur = c.cursor()

# Rockwell PLCs only (server_progid starts with 'Rockwel')
cur.execute("""
    SELECT server_progid, data_type, COUNT(*)
    FROM historian_meta.tag_master
    WHERE server_progid ILIKE 'Rockwel%' AND enabled = true
    GROUP BY server_progid, data_type
    ORDER BY server_progid, data_type
""")
print("=== Rockwell tag count by PLC and data_type ===")
for r in cur.fetchall():
    print(f"  {r[0]:20} {r[1]!r:10} -> {r[2]}")

# Full per-tag dump (the source of truth to diff against the PLC backup)
cur.execute("""
    SELECT server_progid, tag_name, data_type, eng_unit, description
    FROM historian_meta.tag_master
    WHERE server_progid ILIKE 'Rockwel%' AND enabled = true
    ORDER BY server_progid, tag_name
""")
rows = cur.fetchall()
print(f"\n=== Full Rockwell tag list ({len(rows)} tags) ===")
print(f"{'PLC':18} {'TAG':18} {'DATA_TYPE':10} {'UNIT':8} DESCRIPTION")
for r in rows:
    print(f"{r[0]:18} {r[1]:18} {r[2]!r:10} {(r[3] or ''):8} {(r[4] or '')}")

# Write to file for easy diffing
with open('rockwell_tag_types_dump.txt', 'w', encoding='utf-8') as f:
    f.write(f"{'PLC':18} {'TAG':18} {'DATA_TYPE':10} {'UNIT':8} DESCRIPTION\n")
    for r in rows:
        f.write(f"{r[0]:18} {r[1]:18} {r[2]!r:10} {(r[3] or ''):8} {(r[4] or '')}\n")
print("\n[written to rockwell_tag_types_dump.txt]")

c.close()
