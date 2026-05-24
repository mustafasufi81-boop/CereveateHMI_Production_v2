"""Check data points in 24 hours and downsampling behavior"""
import psycopg2
from datetime import datetime, timedelta

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
    
    # Check data points per tag in 24 hours
    print("\n📊 Data points per tag in last 24 hours:")
    cursor.execute("""
        SELECT 
            tag_id,
            COUNT(*) as point_count,
            MIN(time) as earliest,
            MAX(time) as latest,
            EXTRACT(EPOCH FROM (MAX(time) - MIN(time))) as time_span_seconds
        FROM historian_raw.historian_timeseries
        WHERE time >= NOW() - INTERVAL '24 hours'
        GROUP BY tag_id
        ORDER BY point_count DESC
        LIMIT 10
    """)
    
    tags = cursor.fetchall()
    for tag in tags:
        points_per_hour = tag[1] / (tag[4] / 3600) if tag[4] > 0 else 0
        print(f"  {tag[0]:30} {tag[1]:,} points ({points_per_hour:.1f} pts/hr)")
    
    # Check what downsampling does for 24h with max_points=1000
    if tags:
        test_tag = tags[0][0]
        print(f"\n🔬 Testing downsampling for '{test_tag}':")
        
        # Calculate what the query will do
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=24)
        max_points = 1000
        
        # Count total points
        cursor.execute("""
            SELECT COUNT(*) 
            FROM historian_raw.historian_timeseries
            WHERE tag_id = %s
            AND time BETWEEN %s AND %s
        """, (test_tag, start_time, end_time))
        total_count = cursor.fetchone()[0]
        
        print(f"  Total data points: {total_count:,}")
        print(f"  Max points allowed: {max_points}")
        
        if total_count <= max_points:
            print(f"  ✅ Will return ALL {total_count} points (no downsampling)")
        else:
            time_diff_seconds = 24 * 3600
            interval_seconds = max(1, int(time_diff_seconds / max_points))
            print(f"  ⚠️ Will downsample to ~{max_points} points")
            print(f"  Aggregation interval: {interval_seconds} seconds ({interval_seconds/60:.1f} minutes)")
            
            # Test actual downsampled query
            cursor.execute("""
                SELECT COUNT(*) FROM (
                    SELECT 
                        time_bucket(%s::interval, time) AS bucket
                    FROM historian_raw.historian_timeseries
                    WHERE tag_id = %s
                    AND time BETWEEN %s AND %s
                    GROUP BY bucket
                ) as subq
            """, (f"{interval_seconds} seconds", test_tag, start_time, end_time))
            downsampled_count = cursor.fetchone()[0]
            print(f"  Actual downsampled points: {downsampled_count}")
            print(f"  Data reduction: {100*(1-downsampled_count/total_count):.1f}%")
    
    # Check update frequency
    print("\n⏱️  Average update frequency:")
    cursor.execute("""
        SELECT 
            tag_id,
            COUNT(*) as points,
            EXTRACT(EPOCH FROM (MAX(time) - MIN(time)))/COUNT(*) as avg_interval_seconds
        FROM historian_raw.historian_timeseries
        WHERE time >= NOW() - INTERVAL '1 hour'
        GROUP BY tag_id
        ORDER BY avg_interval_seconds
        LIMIT 5
    """)
    
    freq_tags = cursor.fetchall()
    for tag in freq_tags:
        print(f"  {tag[0]:30} {tag[2]:.2f}s interval (~{3600/tag[2]:.0f} pts/hr)")
    
    cursor.close()
    conn.close()
    print("\n✅ Done!")
    
except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()
