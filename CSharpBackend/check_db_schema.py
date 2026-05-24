"""
Check actual database schema before writing
"""
import psycopg2
import json

# Load config
with open('appsettings.json', 'r') as f:
    config = json.load(f)

DB_CONFIG = config['Historian']['Database']['ConnectionString']

def parse_connection_string(conn_str):
    """Parse PostgreSQL connection string"""
    params = {}
    for part in conn_str.split(';'):
        if '=' in part:
            key, value = part.split('=', 1)
            params[key.strip().lower()] = value.strip()
    return params

# Connect
params = parse_connection_string(DB_CONFIG)
print(f"Connecting to: {params.get('host')}:{params.get('port')}/{params.get('database')}")

try:
    conn = psycopg2.connect(
        host=params.get('host', 'localhost'),
        port=int(params.get('port', 5432)),
        database=params.get('database', 'opc_historian'),
        user=params.get('username', 'postgres'),
        password=params.get('password', '')
    )
    print("✅ Connected!\n")
    
    cursor = conn.cursor()
    
    # Check if table exists
    cursor.execute("""
        SELECT table_schema, table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'historian_raw' 
        AND table_name = 'historian_timeseries'
    """)
    
    result = cursor.fetchone()
    if result:
        print(f"✅ Table found: {result[0]}.{result[1]}\n")
        
        # Get column info
        cursor.execute("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_schema = 'historian_raw'
            AND table_name = 'historian_timeseries'
            ORDER BY ordinal_position
        """)
        
        print("COLUMNS:")
        print(f"{'Column Name':<30} {'Data Type':<20} {'Nullable'}")
        print("-" * 70)
        for row in cursor.fetchall():
            print(f"{row[0]:<30} {row[1]:<20} {row[2]}")
        
        # Test INSERT (without actually inserting)
        print("\n\nTEST INSERT SQL:")
        print("-" * 70)
        test_sql = """
        INSERT INTO historian_raw.historian_timeseries 
        (tag_id, time, value_num, quality_code, sample_source, metadata)
        VALUES ('TEST_TAG', NOW(), 123.45, 192, 'OPC_DA', '{"test": true}')
        """
        print(test_sql)
        
        # Check existing data count
        cursor.execute("""
            SELECT COUNT(*), MAX(time) 
            FROM historian_raw.historian_timeseries
        """)
        count, max_time = cursor.fetchone()
        print(f"\n\nEXISTING DATA:")
        print(f"  Total records: {count}")
        print(f"  Latest timestamp: {max_time}")
        
    else:
        print("❌ Table 'historian_raw.historian_timeseries' NOT FOUND")
        
        # List available tables
        cursor.execute("""
            SELECT table_schema, table_name 
            FROM information_schema.tables 
            WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
            ORDER BY table_schema, table_name
        """)
        
        print("\nAvailable tables:")
        for row in cursor.fetchall():
            print(f"  {row[0]}.{row[1]}")
    
    cursor.close()
    conn.close()
    
except Exception as e:
    print(f"❌ Error: {e}")
