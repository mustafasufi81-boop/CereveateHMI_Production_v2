import psycopg2
from datetime import datetime, timedelta

conn = psycopg2.connect('host=localhost port=5432 dbname=Cereveate user=cereveate password=cereveate@222')
cur = conn.cursor()

print("=== PLC TAGS IN DATABASE ===")
cur.execute("""
    SELECT tag_id, COUNT(*) as count, MAX(time) as latest 
    FROM historian_raw.historian_timeseries 
    WHERE tag_id LIKE '%Pump%' OR tag_id LIKE '%Blast%' OR tag_id LIKE '%Boiler%'
    GROUP BY tag_id 
    ORDER BY latest DESC 
    LIMIT 10
""")

result = cur.fetchall()
for row in result:
    print(f'{row[0]:<40} {row[1]:>8} rows, latest: {row[2]}')

print("\n=== RECENT DATA (LAST 5 MINUTES) ===")
five_min_ago = datetime.now() - timedelta(minutes=5)
cur.execute("""
    SELECT COUNT(*) 
    FROM historian_raw.historian_timeseries 
    WHERE time > %s AND (tag_id LIKE '%Pump%' OR tag_id LIKE '%Blast%' OR tag_id LIKE '%Boiler%')
""", (five_min_ago,))

recent_count = cur.fetchone()[0]
print(f"PLC rows in last 5 minutes: {recent_count}")

conn.close()