#!/usr/bin/env python3
"""Apply the plants_areas sync migration."""

import psycopg2
import json

# Load config
with open('config.json') as f:
    config = json.load(f)

db_config = config['database']

# Read migration SQL
with open('migrations/001_sync_plants_areas.sql', 'r', encoding='utf-8') as f:
    migration_sql = f.read()

print("Applying migration: 001_sync_plants_areas.sql")
print("=" * 80)

try:
    conn = psycopg2.connect(
        host=db_config['host'],
        port=db_config['port'],
        database=db_config['database'],
        user=db_config['user'],
        password=db_config['password']
    )
    
    with conn.cursor() as cur:
        cur.execute(migration_sql)
        conn.commit()
    
    print("✅ Migration applied successfully!")
    
    # Verify function exists
    with conn.cursor() as cur:
        cur.execute("""
            SELECT routine_name 
            FROM information_schema.routines 
            WHERE routine_schema='historian_meta' 
              AND routine_name = 'sync_plants_areas_from_tags'
        """)
        func = cur.fetchone()
        if func:
            print(f"✅ Function created: {func[0]}")
        
        # Verify trigger exists
        cur.execute("""
            SELECT tgname 
            FROM pg_trigger 
            WHERE tgname = 'trg_auto_sync_plants_areas'
        """)
        trigger = cur.fetchone()
        if trigger:
            print(f"✅ Trigger created: {trigger[0]}")
    
    conn.close()
    print("\n" + "=" * 80)
    print("Migration complete. Sync system is now active.")
    print("=" * 80)
    
except Exception as e:
    print(f"❌ Migration failed: {e}")
    raise
