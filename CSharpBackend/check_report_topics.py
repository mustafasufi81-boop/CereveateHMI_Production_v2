import psycopg2, psycopg2.extras, json

conn = psycopg2.connect(host='localhost', port=5432, dbname='Automation_DB', user='cereveate', password='cereveate@222')
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

print("=== server_progid groups in tag_master ===")
cur.execute("""
    SELECT server_progid,
           COUNT(*) AS total_tags,
           SUM(CASE WHEN enabled THEN 1 ELSE 0 END) AS enabled_tags,
           array_agg(DISTINCT COALESCE(plant,'NULL') ORDER BY COALESCE(plant,'NULL')) AS plants,
           array_agg(DISTINCT COALESCE(area,'NULL') ORDER BY COALESCE(area,'NULL')) AS areas
    FROM historian_meta.tag_master
    GROUP BY server_progid
    ORDER BY server_progid
""")
for r in cur.fetchall():
    print(dict(r))

print("\n=== Areas with enabled tags + data (current /api/reports/areas result) ===")
cur.execute("""
    SELECT DISTINCT tm.plant, tm.area, tm.server_progid
    FROM historian_meta.tag_master tm
    WHERE tm.plant IS NOT NULL AND tm.area IS NOT NULL AND tm.enabled = TRUE
      AND EXISTS (SELECT 1 FROM historian_raw.historian_timeseries ht WHERE ht.tag_id = tm.tag_id LIMIT 1)
    ORDER BY tm.plant, tm.area
""")
for r in cur.fetchall():
    print(dict(r))

print("\n=== Data in v_daily_hourly_agg by server_progid ===")
cur.execute("""
    SELECT tm.server_progid, COUNT(DISTINCT v.tag_id) AS tags_with_data, COUNT(*) AS agg_rows
    FROM historian_raw.v_daily_hourly_agg v
    JOIN historian_meta.tag_master tm ON tm.tag_id = v.tag_id
    GROUP BY tm.server_progid
    ORDER BY tm.server_progid
""")
for r in cur.fetchall():
    print(dict(r))

conn.close()
