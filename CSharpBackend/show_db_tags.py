import psycopg2

conn = psycopg2.connect(
    host="localhost",
    database="Cereveate",
    user="postgres",
    password="postgres"
)

cur = conn.cursor()
cur.execute("""
    SELECT tag_id, tag_name, enabled 
    FROM historian_meta.tag_master 
    WHERE tag_id LIKE '%Weld%' OR tag_id LIKE '%Joint%' OR tag_id LIKE '%Pipe%' 
       OR tag_id LIKE '%WPS%' OR tag_id LIKE '%Welder%' OR tag_id IN ('Arc','Power','sim_step')
    ORDER BY tag_id
""")

print("\n=== DATABASE tag_master ===")
for row in cur.fetchall():
    print(f"tag_id: {row[0]:25} | tag_name: {row[1]:25} | enabled: {row[2]}")

conn.close()
