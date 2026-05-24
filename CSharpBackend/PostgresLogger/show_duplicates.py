import psycopg2

conn = psycopg2.connect(
    host="localhost",
    port=5432,
    database="Cereveate",
    user="cereveate",
    password="cereveate@222",
)
cur = conn.cursor()
cur.execute(
    """
    SELECT tag_code, "timestamp", COUNT(*)
    FROM sensor_data
    GROUP BY tag_code, "timestamp"
    HAVING COUNT(*) > 1
    ORDER BY COUNT(*) DESC
    LIMIT 5
    """
)
rows = cur.fetchall()
for row in rows:
    print(row)
cur.close()
conn.close()
