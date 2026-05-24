import psycopg2

conn = psycopg2.connect('host=localhost port=5432 dbname=Automation_DB user=cereveate password=cereveate@222')
cur = conn.cursor()

# First show all columns
cur.execute("""
    SELECT column_name FROM information_schema.columns
    WHERE table_schema='historian_meta' AND table_name='tag_master'
    ORDER BY ordinal_position
""")
cols = [r[0] for r in cur.fetchall()]
print("COLUMNS:", cols)
print()

# Show all tags with deadband + interval
cur.execute("SELECT * FROM historian_meta.tag_master ORDER BY tag_id")
rows = cur.fetchall()
print(f"Total tags: {len(rows)}")
print()

# Print header
header = " | ".join(f"{c[:20]:<20}" for c in cols)
print(header)
print("-" * len(header))
for row in rows:
    print(" | ".join(f"{str(v)[:20]:<20}" for v in row))

conn.close()
