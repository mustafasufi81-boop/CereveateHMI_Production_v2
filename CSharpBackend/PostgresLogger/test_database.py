import psycopg2
from datetime import datetime, timedelta

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
    
    # Test connection
    cursor.execute("SELECT version();")
    version = cursor.fetchone()
    print("=" * 80)
    print("✓ Connected Successfully!")
    print("PostgreSQL Version:", version[0])
    print("=" * 80)
    
    # Check if sensor_data table exists
    cursor.execute("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public' 
        ORDER BY table_name;
    """)
    tables = cursor.fetchall()
    print("\n=== TABLES IN DATABASE ===")
    for table in tables:
        print(f"  - {table[0]}")
    
    # Insert test data
    print("\n=== INSERTING TEST DATA ===")
    now = datetime.now()
    
    test_data = [
        (now, 'Plant1', 'Boiler1', 'Temperature', 'T001_Inlet_Temp', 85.5, 'Celsius', 192, 'OK', 'OPC_DA'),
        (now - timedelta(minutes=1), 'Plant1', 'Boiler1', 'Temperature', 'T001_Inlet_Temp', 86.2, 'Celsius', 192, 'OK', 'OPC_DA'),
        (now - timedelta(minutes=2), 'Plant1', 'Boiler1', 'Pressure', 'P001_Steam_Pressure', 120.5, 'Bar', 192, 'OK', 'OPC_DA'),
        (now, 'Plant1', 'Turbine1', 'Vibration', 'V001_Bearing_Vib', 2.3, 'mm/s', 192, 'OK', 'OPC_DA'),
        (now, 'Plant1', 'Generator1', 'Power', 'MW001_Active_Power', 270.5, 'MW', 192, 'OK', 'OPC_DA'),
        (now - timedelta(seconds=30), 'Plant1', 'Boiler1', 'Temperature', 'T002_Outlet_Temp', 125.8, 'Celsius', 192, 'OK', 'OPC_DA'),
        (now, 'Plant1', 'Turbine1', 'Speed', 'S001_Rotor_Speed', 3000, 'RPM', 192, 'OK', 'OPC_DA'),
        (now, 'Plant1', 'Generator1', 'Voltage', 'V002_Line_Voltage', 11.5, 'kV', 192, 'OK', 'OPC_DA'),
    ]
    
    insert_query = """
        INSERT INTO sensor_data 
        (timestamp, plant, asset, subsystem, tag_name, value, unit, quality_code, status_flag, data_source)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    
    cursor.executemany(insert_query, test_data)
    conn.commit()
    print(f"✓ Inserted {len(test_data)} records successfully!")
    
    # Query data back
    print("\n=== QUERYING DATA ===")
    cursor.execute("""
        SELECT 
            timestamp,
            plant,
            asset,
            tag_name,
            value,
            unit,
            quality_code,
            status_flag,
            data_source
        FROM sensor_data
        ORDER BY timestamp DESC
        LIMIT 20;
    """)
    
    results = cursor.fetchall()
    print(f"\nFound {len(results)} records:\n")
    print(f"{'Timestamp':<25} {'Plant':<10} {'Asset':<12} {'Tag':<25} {'Value':<10} {'Unit':<10} {'Quality':<8} {'Status':<8} {'Source':<10}")
    print("-" * 140)
    
    for row in results:
        ts, plant, asset, tag, value, unit, quality, status, source = row
        print(f"{str(ts):<25} {plant:<10} {asset:<12} {tag:<25} {value:<10.2f} {unit:<10} {quality:<8} {status:<8} {source:<10}")
    
    # Get count by tag
    print("\n=== COUNT BY TAG ===")
    cursor.execute("""
        SELECT tag_name, COUNT(*) as count, MIN(value) as min_val, MAX(value) as max_val, AVG(value) as avg_val
        FROM sensor_data
        GROUP BY tag_name
        ORDER BY count DESC;
    """)
    
    tag_counts = cursor.fetchall()
    print(f"\n{'Tag Name':<30} {'Count':<10} {'Min':<12} {'Max':<12} {'Avg':<12}")
    print("-" * 80)
    for row in tag_counts:
        tag, count, min_val, max_val, avg_val = row
        print(f"{tag:<30} {count:<10} {min_val:<12.2f} {max_val:<12.2f} {avg_val:<12.2f}")
    
    # Check if TimescaleDB hypertable is active
    print("\n=== CHECKING TIMESCALEDB STATUS ===")
    try:
        cursor.execute("""
            SELECT hypertable_name, num_dimensions, num_chunks 
            FROM timescaledb_information.hypertables 
            WHERE hypertable_name = 'sensor_data';
        """)
        hypertable = cursor.fetchone()
        if hypertable:
            print(f"✓ TimescaleDB Hypertable Active:")
            print(f"  - Name: {hypertable[0]}")
            print(f"  - Dimensions: {hypertable[1]}")
            print(f"  - Chunks: {hypertable[2]}")
        else:
            print("⚠ sensor_data is NOT a hypertable yet")
            print("  Run setup_timescaledb.sql to convert it")
    except Exception as e:
        print(f"⚠ TimescaleDB extension not available: {e}")
    
    # Total record count
    cursor.execute("SELECT COUNT(*) FROM sensor_data;")
    total = cursor.fetchone()[0]
    print(f"\n=== TOTAL RECORDS IN DATABASE: {total} ===")
    
    cursor.close()
    conn.close()
    
    print("\n" + "=" * 80)
    print("✓ TEST COMPLETED SUCCESSFULLY!")
    print("=" * 80)

except Exception as e:
    print("\n" + "=" * 80)
    print("✗ ERROR:", e)
    print("=" * 80)
    import traceback
    traceback.print_exc()
