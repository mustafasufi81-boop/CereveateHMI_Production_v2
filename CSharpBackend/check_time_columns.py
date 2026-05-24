"""Check which time column has data and the exact column names"""
import psycopg2

db_config = {
    'host': 'localhost',
    'port': 5432,
    'database': 'Cereveate',
    'user': 'cereveate',
    'password': 'cereveate@222'
}

try:
    print("🔌 Connecting to PostgreSQL...")
    conn = psycopg2.connect(**db_config)
    cursor = conn.cursor()
    
    # Check exact schema
    print("\n📋 Exact table schema:")
    cursor.execute("""
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns 
        WHERE table_schema = 'historian_raw' 
        AND table_name = 'historian_timeseries'
        ORDER BY ordinal_position
    """)
    columns = cursor.fetchall()
    for col in columns:
        print(f"  {col[0]:25} {col[1]:25} nullable={col[2]}")
    
    # Sample actual data
    print("\n📊 Sample data (last 3 records):")
    cursor.execute("""
        SELECT * FROM historian_raw.historian_timeseries
        ORDER BY time DESC
        LIMIT 3
    """)
    
    rows = cursor.fetchall()
    col_names = [desc[0] for desc in cursor.description]
    print(f"\nColumns: {col_names}")
    print("\nData:")
    for row in rows:
        print(f"  {row}")
    
    # Check if opc_timestamp has data
    print("\n🕐 Comparing time vs opc_timestamp:")
    cursor.execute("""
        SELECT 
            COUNT(*) as total,
            COUNT(time) as time_count,
            COUNT(opc_timestamp) as opc_time_count,
            MIN(time) as earliest_time,
            MAX(time) as latest_time,
            MIN(opc_timestamp) as earliest_opc,
            MAX(opc_timestamp) as latest_opc
        FROM historian_raw.historian_timeseries
        WHERE time >= NOW() - INTERVAL '1 hour'
    """)
    result = cursor.fetchone()
    print(f"  Total records (last hour): {result[0]}")
    print(f"  time column populated: {result[1]}")
    print(f"  opc_timestamp populated: {result[2]}")
    print(f"  time range: {result[3]} to {result[4]}")
    print(f"  opc_timestamp range: {result[5]} to {result[6]}")
    
    cursor.close()
    conn.close()
    print("\n✅ Done!")
    
except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()
