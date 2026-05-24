"""Check if v_daily_hourly_agg view exists and show its definition"""
import psycopg2

conn = psycopg2.connect(
    host='localhost',
    port=5432,
    dbname='Automation_DB',
    user='cereveate',
    password='cereveate@222'
)
cur = conn.cursor()

# Check if view exists
cur.execute("""
    SELECT EXISTS (
        SELECT 1 
        FROM information_schema.views 
        WHERE table_schema = 'historian_raw' 
        AND table_name = 'v_daily_hourly_agg'
    )
""")
exists = cur.fetchone()[0]
print(f"View exists: {exists}")

if exists:
    # Get view definition
    cur.execute("SELECT pg_get_viewdef('historian_raw.v_daily_hourly_agg', true)")
    definition = cur.fetchone()[0]
    print("\n=== View Definition ===")
    print(definition)
    
    # Check columns
    cur.execute("""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_schema = 'historian_raw' 
        AND table_name = 'v_daily_hourly_agg'
        ORDER BY ordinal_position
    """)
    print("\n=== View Columns ===")
    for row in cur.fetchall():
        print(f"  {row[0]}: {row[1]}")
    
    # Check row count
    cur.execute("SELECT COUNT(*) FROM historian_raw.v_daily_hourly_agg")
    count = cur.fetchone()[0]
    print(f"\n=== Data Check ===")
    print(f"Total rows in view: {count}")
    
    # Check for today's data (2026-05-18)
    cur.execute("""
        SELECT local_date, COUNT(*) as row_count, COUNT(DISTINCT tag_id) as tag_count
        FROM historian_raw.v_daily_hourly_agg
        WHERE local_date >= '2026-05-17'
        GROUP BY local_date
        ORDER BY local_date DESC
    """)
    print("\n=== Recent Data ===")
    for row in cur.fetchall():
        print(f"  Date {row[0]}: {row[1]} rows, {row[2]} tags")
else:
    print("\n❌ VIEW DOES NOT EXIST!")
    print("Need to create it using fix_view_coalesce.py or migrations/010_report_views.sql")

conn.close()
