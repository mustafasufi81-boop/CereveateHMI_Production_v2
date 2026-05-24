import psycopg2
from datetime import datetime

conn = psycopg2.connect(
    host='192.168.0.120',
    port=5432,
    database='Cereveate',
    user='cereveate',
    password='cereveate@222',
    sslmode='disable'
)

cur = conn.cursor()

# Query that shows the CORRECT value based on which column is populated
cur.execute("""
    SELECT 
        last_time,
        tag_id,
        CASE 
            WHEN last_value_bool IS NOT NULL THEN 
                CASE WHEN last_value_bool THEN 'TRUE' ELSE 'FALSE' END
            WHEN last_value_num IS NOT NULL THEN 
                last_value_num::text
            WHEN last_value_text IS NOT NULL THEN 
                last_value_text
            ELSE '[NULL]'
        END as display_value,
        CASE 
            WHEN last_value_bool IS NOT NULL THEN 'BOOL'
            WHEN last_value_num IS NOT NULL THEN 'NUM'
            WHEN last_value_text IS NOT NULL THEN 'TEXT'
            ELSE 'NULL'
        END as value_type
    FROM historian_raw.historian_latest_value
    ORDER BY last_time DESC
    LIMIT 20
""")

print("=" * 100)
print(f"{'Timestamp':<30} {'Tag':<35} {'Value':<20} {'Type':<10}")
print("=" * 100)

for row in cur.fetchall():
    timestamp = row[0].strftime("%Y-%m-%d %H:%M:%S") if row[0] else "N/A"
    print(f"{timestamp:<30} {row[1]:<35} {row[2]:<20} {row[3]:<10}")

cur.close()
conn.close()

print("=" * 100)
print("\nKEY POINTS:")
print("  - Boolean tags (Mem1, Motor_healthy_bit0) now show TRUE/FALSE")
print("  - Numeric tags show their numeric value")
print("  - String tags show their text value")
print("  - [NULL] only appears if ALL value columns are NULL")
