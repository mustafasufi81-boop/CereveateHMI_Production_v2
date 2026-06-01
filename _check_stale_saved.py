"""
BIG QUESTION: Is stale (Uncertain quality) PLC data being SAVED to historian?
This would be misleading - trends/reports would show fake data during disconnect.

PLC froze at 22:47:29. We check if any PLC timeseries rows exist AFTER that time.
"""
import psycopg2
from datetime import datetime

conn = psycopg2.connect(
    host="localhost",
    database="Automation_DB",
    user="cereveate",
    password="cereveate@222"
)
cur = conn.cursor()

print("=" * 70)
print("STALE DATA PERSISTENCE CHECK")
print(f"Current time: {datetime.now().strftime('%H:%M:%S')}")
print("PLC froze at: 22:47:29 (last good read)")
print("=" * 70)

# 1. Find the timeseries table columns first
cur.execute("""
    SELECT column_name 
    FROM information_schema.columns 
    WHERE table_name = 'historian_timeseries' 
      AND table_schema = 'historian_raw'
    ORDER BY ordinal_position
""")
cols = [r[0] for r in cur.fetchall()]
print(f"\nhistorian_timeseries columns: {', '.join(cols)}")

conn.close()
