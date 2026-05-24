import psycopg2

conn = psycopg2.connect('host=localhost dbname=Automation_DB user=cereveate password=cereveate@222')
cur = conn.cursor()

# Check tags for selected plants and areas
cur.execute("""
    SELECT COUNT(*) 
    FROM historian_meta.tag_master 
    WHERE plant IN ('FTP-1', 'PLANT_001', 'Plant1') 
      AND area IN ('AREA_A', 'Area-2', 'Area1', 'POTLINE', 'Production') 
      AND enabled = TRUE
""")
count = cur.fetchone()[0]
print(f"Total enabled tags in selected plants/areas: {count}")

# Check what dates have data
cur.execute("""
    SELECT DATE(time) as date, COUNT(DISTINCT tag_id) as tag_count, COUNT(*) as total_records
    FROM historian_raw.historian_timeseries
    WHERE DATE(time) >= '2026-05-17'
    GROUP BY DATE(time)
    ORDER BY date DESC
    LIMIT 5
""")
dates = cur.fetchall()
print(f"\nData availability:")
for row in dates:
    print(f"  Date: {row[0]}, Tags: {row[1]}, Records: {row[2]}")

cur.close()
conn.close()
