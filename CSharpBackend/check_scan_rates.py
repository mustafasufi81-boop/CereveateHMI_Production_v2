"""Check database for per-tag scan rates"""
import psycopg2

conn = psycopg2.connect(
    host='localhost',
    dbname='Cereveate',
    user='cereveate',
    password='cereveate@222'
)
cur = conn.cursor()

# Check unique scan rates
cur.execute('''
    SELECT plc_polling_interval_ms, COUNT(*) as count
    FROM historian_meta.tag_master 
    WHERE enabled = true
    GROUP BY plc_polling_interval_ms
    ORDER BY plc_polling_interval_ms
''')

print("=" * 50)
print("SCAN RATE DISTRIBUTION:")
print("=" * 50)
print(f"{'ScanRateMs':<15} | {'Tag Count':<10}")
print("-" * 30)
for row in cur.fetchall():
    rate = row[0] if row[0] else "NULL"
    print(f"{rate:<15} | {row[1]:<10}")

# Check some sample tags with their scan rates
cur.execute('''
    SELECT tag_id, plc_polling_interval_ms, deadband_value
    FROM historian_meta.tag_master 
    WHERE enabled = true
    ORDER BY tag_id
    LIMIT 15
''')

print("\n" + "=" * 50)
print("SAMPLE TAGS:")
print("=" * 50)
print(f"{'TagId':<30} | {'ScanMs':<10} | {'Deadband':<10}")
print("-" * 55)
for row in cur.fetchall():
    tag_id = row[0][:28] if len(row[0]) > 28 else row[0]
    scan_ms = row[1] if row[1] else "NULL"
    deadband = row[2] if row[2] else "0"
    print(f"{tag_id:<30} | {scan_ms:<10} | {deadband:<10}")

conn.close()
print("\nDone!")
