"""
Simple check: Which tags raised alarms after 22:40?
Show ONLY the tag names to identify PLC vs OPC source
"""
import psycopg2

conn = psycopg2.connect(
    host="localhost",
    database="Automation_DB",
    user="cereveate",
    password="cereveate@222"
)
cur = conn.cursor()

print("ALARMS AFTER 22:40 (PLC disconnect time):")
print("-" * 60)

cur.execute("""
    SELECT DISTINCT tag_id, COUNT(*) as count
    FROM historian_raw.historian_events
    WHERE time > '2026-05-30 22:40:00'
    GROUP BY tag_id
    ORDER BY count DESC
""")

for tag, count in cur.fetchall():
    print(f"{tag:<30} {count:>5} events")

conn.close()
