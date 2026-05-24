import psycopg2

conn = psycopg2.connect(
    host="localhost",
    port=5432,
    database="Cereveate",
    user="cereveate",
    password="cereveate@222"
)

cur = conn.cursor()

# Check table structure
cur.execute("""
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_schema = 'historian_raw' 
AND table_name = 'historian_timeseries'
ORDER BY ordinal_position;
""")

print("\nTable structure:")
print("="*60)
for col in cur.fetchall():
    print(f"{col[0]:<30} {col[1]}")

# Check if table has primary key or unique constraint
cur.execute("""
SELECT constraint_name, constraint_type
FROM information_schema.table_constraints
WHERE table_schema = 'historian_raw' 
AND table_name = 'historian_timeseries';
""")

print("\nConstraints:")
print("="*60)
constraints = cur.fetchall()
if constraints:
    for c in constraints:
        print(f"{c[0]:<30} {c[1]}")
else:
    print("No constraints found - will use ctid for deletion")

cur.close()
conn.close()
