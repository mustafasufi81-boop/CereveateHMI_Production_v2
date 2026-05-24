import psycopg2

conn = psycopg2.connect(
    host="localhost",
    port=5432,
    database="Automation_DB",
    user="cereveate",
    password="cereveate@222"
)

cursor = conn.cursor()

# This is the EXACT query from report_controller.py
cursor.execute("""
    SELECT DISTINCT
        tm.plant,
        tm.area,
        COALESCE(tm.server_progid, 'Unknown') AS server_progid
    FROM historian_meta.tag_master tm
    WHERE tm.plant IS NOT NULL
        AND tm.area IS NOT NULL
    ORDER BY tm.plant, tm.area, COALESCE(tm.server_progid, 'Unknown')
""")

results = cursor.fetchall()
print(f"Areas API would return {len(results)} rows:")
print()
for plant, area, source in results:
    print(f"  Plant: {plant:15} | Area: {area:15} | Source: {source}")

conn.close()
