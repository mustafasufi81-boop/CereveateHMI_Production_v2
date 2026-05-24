"""Debug why report query returns 0 tags when view has 30 tags for 2026-05-18"""
import psycopg2

conn = psycopg2.connect(
    host='localhost',
    port=5432,
    dbname='Automation_DB',
    user='cereveate',
    password='cereveate@222'
)
cur = conn.cursor()

# Get the tags from tag_master that should be in report
# These are the tags the report_service queries
cur.execute("""
    SELECT tag_id, plant, area, enabled
    FROM historian_meta.tag_master
    WHERE plant IN ('FTP-1', 'PLANT_001', 'Plant1')
    AND area IN ('AREA_A', 'Area-2', 'Area1', 'POTLINE', 'Production')
    AND enabled = true
    ORDER BY tag_id
    LIMIT 10
""")
print("=== Sample enabled tags from tag_master ===")
tag_ids = []
for row in cur.fetchall():
    print(f"  {row[0]}: plant={row[1]}, area={row[2]}, enabled={row[3]}")
    tag_ids.append(row[0])

# Check if these tags exist in the view
if tag_ids:
    cur.execute(f"""
        SELECT tag_id, local_date, COUNT(*) as hour_count
        FROM historian_raw.v_daily_hourly_agg
        WHERE tag_id = ANY(%s)
        AND local_date = '2026-05-18'
        GROUP BY tag_id, local_date
        ORDER BY tag_id
    """, (tag_ids,))
    
    print(f"\n=== These {len(tag_ids)} tags in view for 2026-05-18 ===")
    results = cur.fetchall()
    if results:
        for row in results:
            print(f"  {row[0]}: {row[2]} hours")
    else:
        print("  ❌ NONE OF THESE TAGS FOUND IN VIEW!")
        
        # Check what tags ARE in the view for this date
        cur.execute("""
            SELECT tag_id, COUNT(*) as hour_count
            FROM historian_raw.v_daily_hourly_agg
            WHERE local_date = '2026-05-18'
            GROUP BY tag_id
            ORDER BY tag_id
            LIMIT 10
        """)
        print("\n=== First 10 tags ACTUALLY in view for 2026-05-18 ===")
        for row in cur.fetchall():
            print(f"  {row[0]}: {row[1]} hours")
            
        # Check if it's a plant/area mismatch
        cur.execute("""
            SELECT v.tag_id, tm.plant, tm.area, tm.enabled
            FROM historian_raw.v_daily_hourly_agg v
            LEFT JOIN historian_meta.tag_master tm ON v.tag_id = tm.tag_id
            WHERE v.local_date = '2026-05-18'
            LIMIT 10
        """)
        print("\n=== View tags with their tag_master metadata ===")
        for row in cur.fetchall():
            print(f"  {row[0]}: plant={row[1]}, area={row[2]}, enabled={row[3]}")

# Also check the exact query the report service uses
print("\n=== Simulating exact report_service query ===")
report_date = '2026-05-18'
cur.execute("""
    SELECT DISTINCT tm.tag_id
    FROM historian_meta.tag_master tm
    WHERE tm.plant IN ('FTP-1', 'PLANT_001', 'Plant1')
    AND tm.area IN ('AREA_A', 'Area-2', 'Area1', 'POTLINE', 'Production')
    AND tm.enabled = true
    AND EXISTS (
        SELECT 1 FROM historian_raw.historian_timeseries ht
        WHERE ht.tag_id = tm.tag_id
        LIMIT 1
    )
""")
query_tags = [row[0] for row in cur.fetchall()]
print(f"Tags from query (like report_service line 78-98): {len(query_tags)}")

if query_tags:
    # Now check if these tags have data in the view
    cur.execute("""
        SELECT tag_id, local_date, local_hour, avg_val, max_val, min_val
        FROM historian_raw.v_daily_hourly_agg
        WHERE tag_id = ANY(%s)
        AND local_date = %s
        ORDER BY tag_id, local_hour
        LIMIT 20
    """, (query_tags, report_date))
    
    view_results = cur.fetchall()
    print(f"Results from v_daily_hourly_agg for these tags on {report_date}: {len(view_results)}")
    if view_results:
        print("\nFirst 5 rows:")
        for row in view_results[:5]:
            print(f"  {row[0]} | hour={row[2]} | avg={row[3]}, max={row[4]}, min={row[5]}")
    else:
        print("❌ NO DATA FOUND IN VIEW FOR THESE TAGS!")

conn.close()
