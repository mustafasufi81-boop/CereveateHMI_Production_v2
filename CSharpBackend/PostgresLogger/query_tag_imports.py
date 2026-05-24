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
    SELECT file_path, tag_id, status, records_imported
    FROM tag_imports
    ORDER BY id DESC
    LIMIT 5
    """
)
for row in cur.fetchall():
    print(row)
cur.close()
conn.close()
