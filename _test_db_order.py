"""
Check database order directly
"""
import psycopg2
from psycopg2.extras import RealDictCursor

DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'Automation_DB',
    'user': 'cereveate',
    'password': 'cereveate@222'
}

conn = psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)
cur = conn.cursor()

print("\n" + "="*80)
print("DATABASE QUERY TEST - Event 881456")
print("="*80 + "\n")

# Test the exact query that the API uses
cur.execute("""
    SELECT action_type, action_timestamp
    FROM historian_raw.v_alarm_audit_trail
    WHERE event_id = 881456
    ORDER BY action_timestamp DESC
    LIMIT 10
""")

records = cur.fetchall()

print("First 10 records from database (ORDER BY action_timestamp DESC):")
print("-" * 80)

for i, rec in enumerate(records, 1):
    print(f"{i}. {rec['action_type']:15} | {rec['action_timestamp']}")

print("\n" + "="*80)
print("\nCHECK: Is this descending (newest first)?")

timestamps = [r['action_timestamp'] for r in records]
is_desc = all(timestamps[i] >= timestamps[i+1] for i in range(len(timestamps)-1))

if is_desc:
    print("✅ YES - Database returns DESCENDING order (newest first)")
else:
    print("❌ NO - Database order is wrong")

print("="*80 + "\n")

conn.close()
