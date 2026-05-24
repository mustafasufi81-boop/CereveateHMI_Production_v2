import psycopg2

try:
    conn = psycopg2.connect(
        host='localhost',
        port=5432,
        database='Cereveate',
        user='cereveate',
        password='cereveate@222'
    )
    
    cursor = conn.cursor()
    
    # Check if schema exists
    cursor.execute("""
        SELECT schema_name FROM information_schema.schemata 
        WHERE schema_name = 'historian_meta'
    """)
    schema_exists = cursor.fetchone()
    print(f"Schema 'historian_meta' exists: {schema_exists is not None}")
    
    # Check if table exists
    cursor.execute("""
        SELECT table_name FROM information_schema.tables 
        WHERE table_schema = 'historian_meta' AND table_name = 'tag_master'
    """)
    table_exists = cursor.fetchone()
    print(f"Table 'tag_master' exists: {table_exists is not None}")
    
    if table_exists:
        # Count total tags
        cursor.execute("SELECT COUNT(*) FROM historian_meta.tag_master")
        total = cursor.fetchone()[0]
        print(f"Total tags in tag_master: {total}")
        
        # Count enabled tags
        cursor.execute("SELECT COUNT(*) FROM historian_meta.tag_master WHERE enabled = true")
        enabled = cursor.fetchone()[0]
        print(f"Enabled tags: {enabled}")
        
        # Show first 10 tags
        cursor.execute("""
            SELECT tag_id, tag_name, enabled, data_type 
            FROM historian_meta.tag_master 
            LIMIT 10
        """)
        tags = cursor.fetchall()
        print("\nFirst 10 tags:")
        for tag in tags:
            print(f"  - {tag[0]} | {tag[1]} | Enabled: {tag[2]} | Type: {tag[3]}")
    
    cursor.close()
    conn.close()
    
except Exception as e:
    print(f"Error: {e}")
