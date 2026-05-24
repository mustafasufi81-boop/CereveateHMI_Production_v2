import psycopg2

# Test connection
try:
    conn = psycopg2.connect(
        host='192.168.0.120',
        port=5432,
        database='Cereveate',
        user='cereveate',
        password='cereveate@222'
    )
    
    cur = conn.cursor()
    
    # List all tables
    cur.execute("""
        SELECT schemaname, tablename 
        FROM pg_tables 
        WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
        ORDER BY schemaname, tablename
    """)
    
    tables = cur.fetchall()
    print(f"✅ Connected to database: Cereveate@192.168.0.120")
    print(f"\n📋 Found {len(tables)} tables:\n")
    
    for schema, table in tables:
        print(f"  {schema}.{table}")
    
    # Check for historian tables
    print("\n🔍 Checking for historian tables...")
    cur.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'historian_meta'")
    meta_count = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'historian_raw'")
    raw_count = cur.fetchone()[0]
    
    print(f"  historian_meta schema: {meta_count} tables")
    print(f"  historian_raw schema: {raw_count} tables")
    
    if meta_count > 0 or raw_count > 0:
        print("\n✅ Historian tables EXIST")
        
        # Check tag_master
        try:
            cur.execute("SELECT COUNT(*) FROM historian_meta.tag_master")
            tag_count = cur.fetchone()[0]
            print(f"  historian_meta.tag_master: {tag_count} tags")
        except Exception as e:
            print(f"  ❌ historian_meta.tag_master: {e}")
        
        # Check historian_timeseries
        try:
            cur.execute("SELECT COUNT(*) FROM historian_raw.historian_timeseries")
            data_count = cur.fetchone()[0]
            print(f"  historian_raw.historian_timeseries: {data_count} records")
        except Exception as e:
            print(f"  ❌ historian_raw.historian_timeseries: {e}")
    else:
        print("\n❌ NO historian tables found!")
    
    cur.close()
    conn.close()
    
except Exception as e:
    print(f"❌ Connection ERROR: {e}")
