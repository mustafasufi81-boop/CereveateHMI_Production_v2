import psycopg2

conn = psycopg2.connect(host='localhost', port=5432, dbname='Automation_DB',
                        user='cereveate', password='cereveate@222')
cur = conn.cursor()

print("=== ALL tables in historian_raw and historian_meta ===")
cur.execute("""
    SELECT table_schema, table_name
    FROM information_schema.tables
    WHERE table_schema IN ('historian_raw','historian_meta','public')
    ORDER BY table_schema, table_name
""")
for r in cur.fetchall():
    print(r)

print()
print("=== All columns of EVERY table in historian_raw ===")
cur.execute("""
    SELECT table_name, column_name, data_type
    FROM information_schema.columns
    WHERE table_schema = 'historian_raw'
    ORDER BY table_name, ordinal_position
""")
for r in cur.fetchall():
    print(r)

print()
print("=== All CHECK constraints in historian_raw ===")
cur.execute("""
    SELECT t.relname, c.conname, pg_get_constraintdef(c.oid)
    FROM pg_constraint c
    JOIN pg_class t ON t.oid = c.conrelid
    JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'historian_raw' AND c.contype = 'c'
    ORDER BY t.relname, c.conname
""")
for r in cur.fetchall():
    print(r)

conn.close()
