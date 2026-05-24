import psycopg2

conn = psycopg2.connect(
    host="localhost",
    port=5432,
    database="Cereveate",
    user="cereveate",
    password="cereveate@222",
)
cur = conn.cursor()
cur.execute("SELECT status, COUNT(*) FROM tag_imports GROUP BY status")
for status, count in cur.fetchall():
    print(f"{status}: {count}")
cur.close()
conn.close()
