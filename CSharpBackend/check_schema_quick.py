import psycopg2

conn = psycopg2.connect(
    host='192.168.0.120',
    port=5432,
    database='Cereveate',
    user='cereveate',
    password='cereveate@222',
    sslmode='disable'
)

cur = conn.cursor()

# Check historian_latest_value schema
cur.execute("""
    SELECT column_name, data_type, is_nullable 
    FROM information_schema.columns 
    WHERE table_schema='historian_raw' 
    AND table_name='historian_latest_value' 
    ORDER BY ordinal_position
""")

print("historian_latest_value schema:")
print("=" * 70)
for row in cur.fetchall():
    print(f"{row[0]:30} {row[1]:20} NULL={row[2]}")

print("\n" + "=" * 70)

# Check for actual NULL values in recent data
cur.execute("""
    SELECT tag_id, last_value_num, last_value_text, last_value_bool
    FROM historian_raw.historian_latest_value
    WHERE tag_id IN ('Mem1', 'Mem_2', 'Motor_healthy_bit0')
    ORDER BY tag_id
""")

print("\nRecent data for memory/boolean tags:")
print("=" * 70)
rows = cur.fetchall()
if rows:
    for row in rows:
        print(f"Tag: {row[0]:30} num={row[1]} text={row[2]} bool={row[3]}")
else:
    print("No data found for Mem1, Mem_2, Motor_healthy_bit0")

cur.close()
conn.close()
