import psycopg2

c = psycopg2.connect(host='localhost', database='Automation_DB',
                     user='cereveate', password='cereveate@222')
cur = c.cursor()

# Show the CHECK constraint allowed values
cur.execute("""
    SELECT pg_get_constraintdef(oid)
    FROM pg_constraint
    WHERE conname = 'tag_master_data_type_check'
""")
row = cur.fetchone()
print("=== data_type CHECK constraint ===")
print(row[0] if row else "  (none found)")

# Current Rockwell distribution
cur.execute("""
    SELECT data_type, COUNT(*)
    FROM historian_meta.tag_master
    WHERE server_progid ILIKE 'Rockwel%%' AND enabled = true
    GROUP BY data_type ORDER BY 2 DESC
""")
print("\n=== Rockwell data_type BEFORE ===")
for r in cur.fetchall():
    print(f"  {r[0]!r:10} -> {r[1]}")

# Show the one non-double tag
cur.execute("""
    SELECT tag_id, tag_name, data_type, description
    FROM historian_meta.tag_master
    WHERE server_progid ILIKE 'Rockwel%%' AND enabled = true
      AND lower(data_type) <> 'double'
""")
print("\n=== Non-double Rockwell tags (to be fixed) ===")
for r in cur.fetchall():
    print(f"  tag_id={r[0]} name={r[1]} type={r[2]!r} desc={r[3]!r}")

c.close()
