import psycopg2

conn = psycopg2.connect(host='localhost', database='Cereveate', user='cereveate', password='cereveate@222')
cur = conn.cursor()

print("=== historian_admin.historian_events ===")
cur.execute("""
    SELECT column_name, data_type 
    FROM information_schema.columns 
    WHERE table_schema='historian_admin' AND table_name='historian_events' 
    ORDER BY ordinal_position
""")
for row in cur.fetchall():
    print(f"  {row[0]}: {row[1]}")

print("\n=== historian_admin.writer_checkpoint ===")
cur.execute("""
    SELECT column_name, data_type 
    FROM information_schema.columns 
    WHERE table_schema='historian_admin' AND table_name='writer_checkpoint' 
    ORDER BY ordinal_position
""")
for row in cur.fetchall():
    print(f"  {row[0]}: {row[1]}")

print("\n=== historian_raw.historian_events (if exists) ===")
cur.execute("""
    SELECT column_name, data_type 
    FROM information_schema.columns 
    WHERE table_schema='historian_raw' AND table_name='historian_events' 
    ORDER BY ordinal_position
""")
for row in cur.fetchall():
    print(f"  {row[0]}: {row[1]}")

print("\n=== historian_meta.tag_master (if exists) ===")
cur.execute("""
    SELECT column_name, data_type 
    FROM information_schema.columns 
    WHERE table_schema='historian_meta' AND table_name='tag_master' 
    ORDER BY ordinal_position
""")
print(f"Total columns: {cur.rowcount}")
for row in cur.fetchall():
    print(f"  {row[0]}: {row[1]}")

print("\n=== historian_raw.historian_timeseries (if exists) ===")
cur.execute("""
    SELECT column_name, data_type 
    FROM information_schema.columns 
    WHERE table_schema='historian_raw' AND table_name='historian_timeseries' 
    ORDER BY ordinal_position
""")
for row in cur.fetchall():
    print(f"  {row[0]}: {row[1]}")

print("\n=== All historian_meta tables ===")
cur.execute("""
    SELECT table_name 
    FROM information_schema.tables 
    WHERE table_schema='historian_meta' 
    ORDER BY table_name
""")
for row in cur.fetchall():
    print(f"  {row[0]}")

cur.close()
conn.close()
