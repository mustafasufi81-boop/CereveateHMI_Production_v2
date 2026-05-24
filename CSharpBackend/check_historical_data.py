import psycopg2
from datetime import datetime, timedelta

try:
    conn = psycopg2.connect(
        host='localhost',
        port=5432,
        database='Cereveate',
        user='cereveate',
        password='cereveate@222'
    )
    cur = conn.cursor()
    
    # Check recent data
    cur.execute("""
        SELECT COUNT(*) 
        FROM historian_raw.historian_timeseries 
        WHERE timestamp > NOW() - INTERVAL '1 hour'
    """)
    recent_count = cur.fetchone()[0]
    print(f"✅ Records in last 1 hour: {recent_count}")
    
    # Check total tags
    cur.execute("""
        SELECT COUNT(DISTINCT tag_id) 
        FROM historian_raw.historian_timeseries
    """)
    total_tags = cur.fetchone()[0]
    print(f"✅ Total unique tags in DB: {total_tags}")
    
    # Check most recent data
    cur.execute("""
        SELECT tag_id, MAX(timestamp) as last_time, COUNT(*) as count
        FROM historian_raw.historian_timeseries
        GROUP BY tag_id
        ORDER BY last_time DESC
        LIMIT 10
    """)
    print("\n📊 Most recent tags:")
    for row in cur.fetchall():
        print(f"  {row[0]}: Last update {row[1]} ({row[2]} total records)")
    
    # Check if there's data from the tags in your selection
    test_tags = ['@ClientCount', 'Bucket Brigade.Real4', 'Random.Int8']
    cur.execute("""
        SELECT tag_id, COUNT(*), 
               MIN(timestamp) as first_time, 
               MAX(timestamp) as last_time
        FROM historian_raw.historian_timeseries
        WHERE tag_id = ANY(%s)
        GROUP BY tag_id
    """, (test_tags,))
    
    print(f"\n🔍 Checking specific tags: {test_tags}")
    results = cur.fetchall()
    if results:
        for row in results:
            print(f"  {row[0]}: {row[1]} records, {row[2]} to {row[3]}")
    else:
        print("  ⚠️ No data found for these tags!")
    
    conn.close()
    
except Exception as e:
    print(f"❌ Error: {e}")
