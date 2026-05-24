import psycopg2

conn = psycopg2.connect(host='localhost', dbname='Automation_DB', user='cereveate', password='cereveate@222')

# Check all schemas
cur2 = conn.cursor()
cur2.execute("SELECT schema_name FROM information_schema.schemata")
print("Schemas:", cur2.fetchall())
cur = conn.cursor()

# Find users table
cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name LIKE '%user%'")
print("User tables:", cur.fetchall())

# Check all tables
cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
print("All tables:", cur.fetchall())

conn.close()
