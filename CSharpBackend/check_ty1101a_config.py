import psycopg2

c = psycopg2.connect('host=localhost dbname=Automation_DB user=cereveate password=cereveate@222')
cur = c.cursor()

# All tables across all schemas that might be relevant
cur.execute("""
    SELECT table_schema, table_name FROM information_schema.tables
    WHERE table_schema NOT IN ('information_schema','pg_catalog','pg_toast')
    ORDER BY table_schema, table_name
""")
print("ALL TABLES:")
for r in cur.fetchall(): print(f"  {r[0]}.{r[1]}")

# Columns of historian_meta.tag_master
cur.execute("""
    SELECT column_name FROM information_schema.columns
    WHERE table_schema='historian_meta' AND table_name='tag_master'
    ORDER BY ordinal_position
""")
cols = [r[0] for r in cur.fetchall()]
print("\ntag_master COLUMNS:", cols)

# TY1101A row
cur.execute("SELECT * FROM historian_meta.tag_master WHERE tag_id='TY1101A'")
row = cur.fetchone()
if row:
    print("\nTY1101A tag_master:")
    for col, val in zip(cols, row): print(f"  {col}: {val!r}")
else:
    print("TY1101A not in historian_meta.tag_master")

c.close()

# Get full TY1101A config as reference
cur.execute("""
    SELECT column_name FROM information_schema.columns
    WHERE table_schema = 'historian_raw' AND table_name = 'tag_master'
    ORDER BY ordinal_position
""")
cols = [r[0] for r in cur.fetchall()]
print("COLUMNS:", cols)
print()

cur.execute("SELECT * FROM historian_raw.tag_master WHERE tag_id = 'TY1101A'")
row = cur.fetchone()
if row:
    for col, val in zip(cols, row):
        print(f"  {col}: {val!r}")

# Also check alarm_config for TY1101A
cur.execute("""
    SELECT column_name FROM information_schema.columns
    WHERE table_schema = 'historian_raw' AND table_name = 'alarm_config'
    ORDER BY ordinal_position
""")
alarm_cols = [r[0] for r in cur.fetchall()]
print("\nALARM_CONFIG COLUMNS:", alarm_cols)

cur.execute("SELECT * FROM historian_raw.alarm_config WHERE tag_id = 'TY1101A'")
row = cur.fetchone()
if row:
    print("TY1101A alarm_config:")
    for col, val in zip(alarm_cols, row):
        print(f"  {col}: {val!r}")
else:
    print("No alarm_config row for TY1101A")

c.close()
