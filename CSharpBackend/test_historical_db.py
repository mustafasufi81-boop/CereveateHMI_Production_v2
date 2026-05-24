"""Test historical data query from database"""
import psycopg2
from datetime import datetime, timedelta

# Database config
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
    
    # Check table schema
    print("\n📋 Checking historian_timeseries schema...")
    cursor.execute("""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_schema = 'historian_raw' 
        AND table_name = 'historian_timeseries'
        ORDER BY ordinal_position
    """)
    columns = cursor.fetchall()
    print("Columns:")
    for col in columns:
        print(f"  - {col[0]}: {col[1]}")
    
    # Count total records
    print("\n📊 Counting total records...")
    cursor.execute("SELECT COUNT(*) FROM historian_raw.historian_timeseries")
    total_count = cursor.fetchone()[0]
    print(f"Total records: {total_count:,}")
    
    # Check recent data (last 24 hours)
    print("\n🕐 Checking last 24 hours data...")
    cursor.execute("""
        SELECT COUNT(*), MIN(timestamp), MAX(timestamp)
        FROM historian_raw.historian_timeseries
        WHERE timestamp >= NOW() - INTERVAL '24 hours'
    """)
    result = cursor.fetchone()
    print(f"Records in last 24h: {result[0]:,}")
    print(f"Earliest: {result[1]}")
    print(f"Latest: {result[2]}")
    
    # Check unique tags
    print("\n🏷️  Checking unique tags...")
    cursor.execute("""
        SELECT tag_id, COUNT(*) as count
        FROM historian_raw.historian_timeseries
        WHERE timestamp >= NOW() - INTERVAL '1 hour'
        GROUP BY tag_id
        ORDER BY count DESC
        LIMIT 10
    """)
    tags = cursor.fetchall()
    print("Top 10 tags in last hour:")
    for tag in tags:
        print(f"  - {tag[0]}: {tag[1]:,} records")
    
    # Sample data from one tag
    print("\n📝 Sample data from first tag...")
    if tags:
        first_tag = tags[0][0]
        cursor.execute("""
            SELECT timestamp, value, quality_code
            FROM historian_raw.historian_timeseries
            WHERE tag_id = %s
            ORDER BY timestamp DESC
            LIMIT 5
        """, (first_tag,))
        samples = cursor.fetchall()
        print(f"Last 5 records for '{first_tag}':")
        for sample in samples:
            print(f"  {sample[0]}: {sample[1]} (quality: {sample[2]})")
    
    cursor.close()
    conn.close()
    print("\n✅ Test complete!")
    
except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()
