import psycopg2
import json

# Load correct credentials from config.json
with open('config.json', 'r') as f:
    config = json.load(f)

db_config = config['database']
conn = psycopg2.connect(
    host=db_config['host'],
    port=db_config['port'],
    database=db_config['database'],
    user=db_config['user'],
    password=db_config['password']
)
cur = conn.cursor()

print("=" * 80)
print("REPORT SYSTEM AUDIT")
print("=" * 80)

# 1. Check report template tables/views
print("\n1. REPORT TEMPLATE TABLES/VIEWS:")
cur.execute("""
    SELECT table_name, table_type 
    FROM information_schema.tables 
    WHERE table_schema = 'historian_meta' 
    AND table_name LIKE '%report%'
    ORDER BY table_name
""")
for row in cur.fetchall():
    print(f"   - {row[0]} ({row[1]})")

# 2. Check v_report_template_tags structure
print("\n2. v_report_template_tags STRUCTURE:")
cur.execute("""
    SELECT column_name, data_type 
    FROM information_schema.columns 
    WHERE table_schema = 'historian_meta' 
    AND table_name = 'v_report_template_tags'
    ORDER BY ordinal_position
""")
for row in cur.fetchall():
    print(f"   - {row[0]}: {row[1]}")

# 3. Sample data from v_report_template_tags
print("\n3. SAMPLE v_report_template_tags DATA (DAILY):")
cur.execute("""
    SELECT s_no, tag_id, display_label, report_type, plant, area
    FROM historian_meta.v_report_template_tags
    WHERE report_type = 'DAILY'
    ORDER BY s_no
    LIMIT 5
""")
for row in cur.fetchall():
    print(f"   {row}")

# 4. Check shift definitions
print("\n4. SHIFT DEFINITIONS:")
cur.execute("""
    SELECT table_name 
    FROM information_schema.tables 
    WHERE table_schema = 'historian_meta' 
    AND table_name LIKE '%shift%'
""")
shift_tables = cur.fetchall()
for row in shift_tables:
    print(f"   - {row[0]}")
    
if shift_tables:
    cur.execute(f"SELECT * FROM historian_meta.{shift_tables[0][0]} LIMIT 3")
    for row in cur.fetchall():
        print(f"     {row}")

# 5. Check historian_data table
print("\n5. HISTORIAN DATA SCHEMA:")
cur.execute("""
    SELECT schema_name 
    FROM information_schema.schemata 
    WHERE schema_name LIKE '%histor%'
""")
schemas = cur.fetchall()
for row in schemas:
    print(f"   Schema: {row[0]}")
    cur.execute(f"""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = '{row[0]}'
        AND table_type = 'BASE TABLE'
        LIMIT 5
    """)
    for tbl in cur.fetchall():
        print(f"      - {tbl[0]}")

# 6. Sample historian data
print("\n6. SAMPLE HISTORIAN DATA (Latest 3 records):")
try:
    cur.execute("""
        SELECT tag_id, timestamp, value, quality 
        FROM historian_raw.historian_latest_value 
        ORDER BY timestamp DESC 
        LIMIT 3
    """)
    for row in cur.fetchall():
        print(f"   {row}")
except Exception as e:
    print(f"   Error: {e}")
    conn.rollback()

# 7. Check report procedures/functions
print("\n7. REPORT PROCEDURES/FUNCTIONS:")
cur.execute("""
    SELECT routine_name, routine_type 
    FROM information_schema.routines 
    WHERE routine_schema = 'historian_meta' 
    AND routine_name LIKE '%report%'
""")
for row in cur.fetchall():
    print(f"   - {row[0]} ({row[1]})")

cur.close()
conn.close()

print("\n" + "=" * 80)
print("AUDIT COMPLETE")
print("=" * 80)
