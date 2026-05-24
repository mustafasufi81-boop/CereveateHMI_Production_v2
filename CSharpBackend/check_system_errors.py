import psycopg2

conn = psycopg2.connect(
    host="localhost",
    port=5432,
    database="Cereveate",
    user="cereveate",
    password="cereveate@222"
)

cur = conn.cursor()

print("\n" + "="*80)
print("CHECKING HISTORIAN SYSTEM ERRORS")
print("="*80)

# Check if events log table exists
try:
    cur.execute("""
    SELECT COUNT(*) 
    FROM information_schema.tables 
    WHERE table_schema = 'historian_admin' 
    AND table_name = 'events';
    """)
    
    if cur.fetchone()[0] > 0:
        print("\n📋 Recent Errors from historian_admin.events:")
        print("="*80)
        
        cur.execute("""
        SELECT 
            created_at,
            event_type,
            severity,
            message,
            writer_name
        FROM historian_admin.events
        WHERE severity IN ('ERROR', 'WARNING')
        ORDER BY created_at DESC
        LIMIT 20;
        """)
        
        errors = cur.fetchall()
        if errors:
            for row in errors:
                print(f"\n[{row[0]}] {row[2]} - {row[1]}")
                print(f"  Writer: {row[4]}")
                print(f"  Message: {row[3]}")
        else:
            print("No errors found in events table")
    else:
        print("❌ historian_admin.events table not found")
        
except Exception as e:
    print(f"Error checking events: {e}")

# Check for database connection issues
print("\n" + "="*80)
print("DATABASE CONNECTION TEST")
print("="*80)

try:
    cur.execute("SELECT version();")
    version = cur.fetchone()[0]
    print(f"✅ PostgreSQL: {version}")
    
    cur.execute("SELECT current_database();")
    db = cur.fetchone()[0]
    print(f"✅ Database: {db}")
    
    cur.execute("SELECT current_user;")
    user = cur.fetchone()[0]
    print(f"✅ User: {user}")
    
except Exception as e:
    print(f"❌ Connection test failed: {e}")

# Check table write permissions
print("\n" + "="*80)
print("TABLE PERMISSIONS CHECK")
print("="*80)

try:
    cur.execute("""
    SELECT 
        grantee,
        privilege_type
    FROM information_schema.role_table_grants
    WHERE table_schema = 'historian_raw'
    AND table_name = 'historian_timeseries'
    AND grantee = current_user;
    """)
    
    perms = cur.fetchall()
    if perms:
        print("✅ Permissions for historian_timeseries:")
        for p in perms:
            print(f"   - {p[1]}")
    else:
        print("⚠️ No permissions found for current user")
        
except Exception as e:
    print(f"❌ Permission check failed: {e}")

# Check if writer is blocked by locks
print("\n" + "="*80)
print("ACTIVE LOCKS CHECK")
print("="*80)

try:
    cur.execute("""
    SELECT 
        pid,
        usename,
        application_name,
        state,
        query_start,
        state_change,
        wait_event_type,
        wait_event,
        LEFT(query, 100) as query
    FROM pg_stat_activity
    WHERE datname = 'Cereveate'
    AND state != 'idle'
    ORDER BY query_start;
    """)
    
    locks = cur.fetchall()
    if locks:
        print(f"Found {len(locks)} active connections:")
        for lock in locks:
            print(f"\nPID: {lock[0]}, User: {lock[1]}, App: {lock[2]}")
            print(f"  State: {lock[3]}, Wait: {lock[6]}/{lock[7]}")
            print(f"  Query: {lock[8]}")
    else:
        print("✅ No active connections found")
        
except Exception as e:
    print(f"❌ Lock check failed: {e}")

# Check recent write activity
print("\n" + "="*80)
print("RECENT WRITE ACTIVITY")
print("="*80)

try:
    cur.execute("""
    SELECT 
        tag_id,
        MAX(time) as last_write,
        COUNT(*) as count_last_minute
    FROM historian_raw.historian_timeseries
    WHERE time > NOW() - INTERVAL '1 minute'
    GROUP BY tag_id
    ORDER BY last_write DESC;
    """)
    
    recent = cur.fetchall()
    if recent:
        print(f"Writes in last minute for {len(recent)} tags:")
        for r in recent[:10]:
            print(f"  {r[0]}: {r[2]} rows, last @ {r[1]}")
    else:
        print("⚠️ NO WRITES in last minute!")
        
except Exception as e:
    print(f"Error checking writes: {e}")

cur.close()
conn.close()

print("\n" + "="*80)
print("Check complete")
print("="*80)
