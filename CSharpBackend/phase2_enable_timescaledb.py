"""
Phase 2+3 combined: Enable TimescaleDB in Automation_DB.
shared_preload_libraries already has 'timescaledb' — no restart needed.
Just run CREATE EXTENSION.
"""
import psycopg2

conn = psycopg2.connect(host='localhost', port=5432, dbname='Automation_DB', user='cereveate', password='cereveate@222')
conn.autocommit = True
cur = conn.cursor()

print("=" * 60)
print("Enabling TimescaleDB in Automation_DB...")
print("=" * 60)

cur.execute("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;")
print("CREATE EXTENSION done.")

# Verify
cur.execute("SELECT extname, extversion FROM pg_extension WHERE extname = 'timescaledb';")
row = cur.fetchone()
if row:
    print(f"\n✅ TimescaleDB ENABLED — version {row[1]}")
else:
    print("\n❌ Extension not found after CREATE — something went wrong.")

cur.close()
conn.close()
