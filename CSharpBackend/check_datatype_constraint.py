import psycopg2

conn = psycopg2.connect(
    host='localhost',
    database='Cereveate',
    user='cereveate',
    password='cereveate@222'
)

cur = conn.cursor()

# Check what data types are allowed
cur.execute("""
    SELECT pg_get_constraintdef(con.oid) 
    FROM pg_constraint con
    JOIN pg_class rel ON rel.oid = con.conrelid
    WHERE conname = 'tag_master_data_type_check'
      AND rel.relname = 'tag_master'
""")

constraint_def = cur.fetchone()
if constraint_def:
    print("\n" + "="*80)
    print("TAG_MASTER DATA_TYPE CHECK CONSTRAINT:")
    print("="*80)
    print(constraint_def[0])
    print("="*80)
else:
    print("Constraint not found")

cur.close()
conn.close()
