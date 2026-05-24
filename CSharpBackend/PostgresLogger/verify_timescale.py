import psycopg2

conn = psycopg2.connect(
    host="localhost",
    port="5432",
    database="Cereveate",
    user="cereveate",
    password="cereveate@222"
)

cursor = conn.cursor()

print("=" * 80)
print("TIMESCALEDB SETUP CHECK")
print("=" * 80)

# Check TimescaleDB extension
print("\n1. Checking TimescaleDB extension...")
cursor.execute("SELECT extname, extversion FROM pg_extension WHERE extname = 'timescaledb';")
result = cursor.fetchone()

if result:
    print(f"   ✓ TimescaleDB {result[1]} installed")
else:
    print("   ✗ TimescaleDB NOT installed - trying to install...")
    try:
        cursor.execute("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;")
        conn.commit()
        print("   ✓ Installed!")
    except Exception as e:
        print(f"   ✗ Failed: {e}")
        print("   Run as superuser: CREATE EXTENSION timescaledb;")

# Check if sensor_data is hypertable
print("\n2. Checking sensor_data hypertable...")
try:
    cursor.execute("""
        SELECT hypertable_name, num_chunks 
        FROM timescaledb_information.hypertables 
        WHERE hypertable_name = 'sensor_data';
    """)
    ht = cursor.fetchone()
    
    if ht:
        print(f"   ✓ sensor_data is hypertable with {ht[1]} chunks")
    else:
        print("   ✗ NOT a hypertable - converting...")
        cursor.execute("""
            SELECT create_hypertable('sensor_data', 'timestamp', 
                chunk_time_interval => INTERVAL '1 day', if_not_exists => TRUE);
        """)
        conn.commit()
        print("   ✓ Converted to hypertable!")
except Exception as e:
    print(f"   Error: {e}")

# Check row count
cursor.execute("SELECT COUNT(*) FROM sensor_data;")
print(f"\n3. Total rows in sensor_data: {cursor.fetchone()[0]}")

cursor.close()
conn.close()

print("\n" + "=" * 80)
print("✓ DONE")
print("=" * 80)
