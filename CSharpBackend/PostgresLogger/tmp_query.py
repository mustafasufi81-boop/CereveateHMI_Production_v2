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
    SELECT tag_code, COUNT(*) AS duplicate_rows
    FROM (
        SELECT tag_code, "timestamp"
        FROM sensor_data
        GROUP BY tag_code, "timestamp"
        HAVING COUNT(*) > 1
    ) dup
    GROUP BY tag_code
    ORDER BY duplicate_rows DESC
    LIMIT 5
    """
)
for row in cur.fetchall():
    print(row)
cur.close()
conn.close()
