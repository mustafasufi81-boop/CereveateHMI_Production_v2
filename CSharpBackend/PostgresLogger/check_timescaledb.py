import psycopg2

try:
    # Connect to PostgreSQL
    conn = psycopg2.connect(
        host="localhost",
        port="5432",
        database="Cereveate",
        user="cereveate",
        password="cereveate@222"
    )
    
    cursor = conn.cursor()
    
    print("=" * 80)
    print("CHECKING TIMESCALEDB STATUS")
    print("=" * 80)
    
    # Check if TimescaleDB extension exists
    cursor.execute("""
        SELECT extname, extversion 
        FROM pg_extension 
        WHERE extname = 'timescaledb';
    """)
    
    result = cursor.fetchone()
    if result:
        print(f"\n✓ TimescaleDB Extension: INSTALLED")
        print(f"  Version: {result[1]}")
    else:
        print(f"\n✗ TimescaleDB Extension: NOT INSTALLED")
        print("\nTo install TimescaleDB:")
        print("  1. Run as postgres superuser:")
        print("     CREATE EXTENSION IF NOT EXISTS timescaledb;")
    
    # Check if sensor_data is a hypertable
    try:
        cursor.execute("""
            SELECT hypertable_schema, hypertable_name, num_dimensions, num_chunks
            FROM timescaledb_information.hypertables
            WHERE hypertable_name = 'sensor_data';
        """)
        
        hypertable = cursor.fetchone()
        if hypertable:
            print(f"\n✓ sensor_data: IS A HYPERTABLE")
            print(f"  Schema: {hypertable[0]}")
            print(f"  Name: {hypertable[1]}")
            print(f"  Dimensions: {hypertable[2]}")
            print(f"  Chunks: {hypertable[3]}")
        else:
            print(f"\n✗ sensor_data: NOT A HYPERTABLE")
            print("\nTo convert to hypertable, run:")
            print("  SELECT create_hypertable('sensor_data', 'timestamp',")
            print("    chunk_time_interval => INTERVAL '1 day',")
            print("    if_not_exists => TRUE);")
    except Exception as e:
        print(f"\n⚠ Cannot check hypertable status: {e}")
        print("  TimescaleDB extension may not be enabled")
    
    # Check table structure
    cursor.execute("""
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_name = 'sensor_data'
        ORDER BY ordinal_position;
    """)
    
    columns = cursor.fetchall()
    print(f"\n=== sensor_data TABLE STRUCTURE ===")
    print(f"{'Column':<30} {'Type':<30} {'Nullable':<10}")
    print("-" * 70)
    for col in columns:
        print(f"{col[0]:<30} {col[1]:<30} {col[2]:<10}")
    
    # Check record count
    cursor.execute("SELECT COUNT(*) FROM sensor_data;")
    count = cursor.fetchone()[0]
    print(f"\nTotal Records: {count}")
    
    # Check if indexes exist
    cursor.execute("""
        SELECT indexname, indexdef
        FROM pg_indexes
        WHERE tablename = 'sensor_data'
        ORDER BY indexname;
    """)
    
    indexes = cursor.fetchall()
    print(f"\n=== INDEXES ({len(indexes)}) ===")
    for idx in indexes:
        print(f"  - {idx[0]}")
    
    cursor.close()
    conn.close()
    
    print("\n" + "=" * 80)

except Exception as e:
    print(f"\n✗ ERROR: {e}")
    import traceback
    traceback.print_exc()
