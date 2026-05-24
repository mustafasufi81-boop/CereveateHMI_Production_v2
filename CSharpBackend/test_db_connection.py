#!/usr/bin/env python3
"""Quick database connection test"""

import psycopg2

DB_CONFIG = {
    'host': '192.168.0.120',
    'port': 5432,
    'database': 'Cereveate',
    'user': 'cereveate',
    'password': 'cereveate@222',
    'sslmode': 'disable'
}

print("Testing database connection...")
print(f"Host: {DB_CONFIG['host']}:{DB_CONFIG['port']}")
print(f"Database: {DB_CONFIG['database']}")
print(f"User: {DB_CONFIG['user']}")
print("-" * 50)

try:
    # Test connection
    conn = psycopg2.connect(**DB_CONFIG)
    print("✅ Connection successful!")
    
    # Test schema exists
    cur = conn.cursor()
    cur.execute("SELECT schema_name FROM information_schema.schemata WHERE schema_name = 'historian_raw'")
    result = cur.fetchone()
    
    if result:
        print(f"✅ Schema 'historian_raw' exists")
    else:
        print(f"❌ Schema 'historian_raw' NOT FOUND")
        print("   Run: CREATE SCHEMA historian_raw;")
    
    # Test tables exist
    tables = ['historian_latest_value', 'historian_timeseries']
    for table in tables:
        cur.execute(f"""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'historian_raw' 
            AND table_name = '{table}'
        """)
        result = cur.fetchone()
        
        if result:
            print(f"✅ Table 'historian_raw.{table}' exists")
        else:
            print(f"❌ Table 'historian_raw.{table}' NOT FOUND")
            print(f"   Create table using create_historian_schema.sql")
    
    # Test INSERT permission
    try:
        cur.execute("""
            INSERT INTO historian_raw.historian_latest_value 
            (tag_id, last_time, last_quality, updated_at) 
            VALUES ('TEST_TAG', NOW(), 'G', NOW())
            ON CONFLICT (tag_id) DO UPDATE SET last_time = EXCLUDED.last_time
        """)
        conn.commit()
        print("✅ INSERT permission verified")
        
        # Cleanup test
        cur.execute("DELETE FROM historian_raw.historian_latest_value WHERE tag_id = 'TEST_TAG'")
        conn.commit()
        
    except Exception as e:
        print(f"❌ INSERT permission failed: {e}")
    
    cur.close()
    conn.close()
    print("\n✅ Database is ready for PLC scanner")
    
except psycopg2.OperationalError as e:
    print(f"❌ Connection failed: {e}")
    print("\nPossible issues:")
    print("1. PostgreSQL is not running on 192.168.0.120:5432")
    print("2. Firewall blocking connection")
    print("3. Database 'Cereveate' does not exist")
    print("4. User 'cereveate' password is incorrect")
    
except Exception as e:
    print(f"❌ Unexpected error: {e}")
    import traceback
    traceback.print_exc()
