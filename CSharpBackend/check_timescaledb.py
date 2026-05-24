import psycopg2

conn = psycopg2.connect(host='localhost', port=5432, dbname='Automation_DB', user='cereveate', password='cereveate@222')
cur = conn.cursor()

cur.execute("SELECT name, default_version, installed_version FROM pg_available_extensions WHERE name = 'timescaledb';")
row = cur.fetchone()
if row:
    print(f"Extension:         {row[0]}")
    print(f"Available version: {row[1]}")
    print(f"Installed version: {row[2]}")
    if row[2]:
        print("STATUS: ✅ INSTALLED AND ENABLED in this database")
    else:
        print("STATUS: ⚠️  Package exists on server but NOT yet enabled in Automation_DB")
        print("         Run: CREATE EXTENSION IF NOT EXISTS timescaledb;")
else:
    print("STATUS: ❌ NOT AVAILABLE — TimescaleDB package is NOT installed on this PostgreSQL server")
    print("         Download from: https://docs.timescale.com/self-hosted/latest/install/installation-windows/")

cur.close()
conn.close()
