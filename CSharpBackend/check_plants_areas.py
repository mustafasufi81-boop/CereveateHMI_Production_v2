import psycopg2

conn = psycopg2.connect(
    host="localhost",
    port=5432,
    database="Automation_DB",
    user="postgres",
    password="admin"
)

cursor = conn.cursor()

# Check distinct plants and areas with data on 2026-05-18
query = """
SELECT DISTINCT tm.plant, tm.area
FROM historian_raw.v_daily_hourly_agg v
JOIN historian_meta.tag_master tm ON v.tag_id = tm.tag_id
WHERE v.local_date = '2026-05-18'
ORDER BY tm.plant, tm.area;
"""

cursor.execute(query)
rows = cursor.fetchall()

print("=== Plants and Areas with data on 2026-05-18 ===")
for plant, area in rows:
    print(f"Plant: '{plant}' | Area: '{area}'")

cursor.close()
conn.close()
