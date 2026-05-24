"""Test query performance for different time ranges and sampling intervals"""
import psycopg2
import time
from datetime import datetime, timedelta

db_config = {
    'host': 'localhost',
    'port': 5432,
    'database': 'Cereveate',
    'user': 'cereveate',
    'password': 'cereveate@222'
}

def test_query_performance(hours, sampling_interval_seconds):
    """Test a single query configuration"""
    try:
        conn = psycopg2.connect(**db_config)
        cursor = conn.cursor()
        
        # Get a sample tag
        cursor.execute("""
            SELECT tag_id FROM historian_raw.historian_timeseries 
            WHERE time >= NOW() - INTERVAL '24 hours'
            GROUP BY tag_id 
            ORDER BY COUNT(*) DESC 
            LIMIT 1
        """)
        tag_id = cursor.fetchone()[0]
        
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=hours)
        
        # Calculate max points
        total_seconds = hours * 3600
        max_points = total_seconds // sampling_interval_seconds
        
        print(f"\n{'='*80}")
        print(f"Testing: {hours}h range, {sampling_interval_seconds}s interval")
        print(f"Tag: {tag_id}")
        print(f"Expected max points: {max_points:,}")
        print(f"Time range: {start_time} to {end_time}")
        
        # Count total data points
        start = time.time()
        cursor.execute("""
            SELECT COUNT(*) 
            FROM historian_raw.historian_timeseries
            WHERE tag_id = %s
            AND time BETWEEN %s AND %s
        """, (tag_id, start_time, end_time))
        total_count = cursor.fetchone()[0]
        count_time = time.time() - start
        
        print(f"Total raw data points: {total_count:,} (counted in {count_time:.3f}s)")
        
        # Test downsampled query
        start = time.time()
        interval = f"{sampling_interval_seconds} seconds"
        cursor.execute("""
            SELECT 
                time_bucket(%s::interval, time) AS bucket,
                AVG(value_num) as value,
                MAX(quality) as quality
            FROM historian_raw.historian_timeseries
            WHERE tag_id = %s
            AND time BETWEEN %s AND %s
            GROUP BY bucket
            ORDER BY bucket ASC
        """, (interval, tag_id, start_time, end_time))
        
        results = cursor.fetchall()
        query_time = time.time() - start
        
        actual_points = len(results)
        reduction = 100 * (1 - actual_points / max(total_count, 1))
        
        print(f"Downsampled points: {actual_points:,}")
        print(f"Data reduction: {reduction:.1f}%")
        print(f"Query time: {query_time:.3f}s")
        print(f"Performance: {actual_points/query_time:.0f} points/sec")
        
        # Calculate memory estimate
        bytes_per_point = 32  # timestamp + value + quality
        memory_mb = (actual_points * bytes_per_point) / (1024 * 1024)
        print(f"Estimated memory: {memory_mb:.2f} MB")
        
        # Performance rating
        if query_time < 1:
            rating = "⚡ EXCELLENT"
        elif query_time < 3:
            rating = "✅ GOOD"
        elif query_time < 10:
            rating = "⚠️ ACCEPTABLE"
        else:
            rating = "❌ SLOW"
        
        print(f"Rating: {rating}")
        
        cursor.close()
        conn.close()
        
        return {
            'hours': hours,
            'interval': sampling_interval_seconds,
            'total_count': total_count,
            'actual_points': actual_points,
            'query_time': query_time,
            'memory_mb': memory_mb
        }
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return None

if __name__ == "__main__":
    print("🔬 OPC Historian Query Performance Test")
    print("="*80)
    
    # Test configurations (hours, sampling_interval_seconds)
    test_cases = [
        # Short ranges - high detail
        (1, 5),      # 1 hour @ 5s = 720 points
        (6, 5),      # 6 hours @ 5s = 4,320 points
        (24, 5),     # 1 day @ 5s = 17,280 points
        
        # Medium ranges
        (168, 30),   # 1 week @ 30s = 20,160 points
        (336, 60),   # 2 weeks @ 1min = 20,160 points
        (720, 600),  # 1 month @ 10min = 4,320 points
        
        # Long ranges
        (1440, 600), # 2 months @ 10min = 8,640 points
        (2160, 1800),# 3 months @ 30min = 4,320 points
        (4320, 1800),# 6 months @ 30min = 8,640 points
        (8760, 3600),# 1 year @ 1hour = 8,760 points
    ]
    
    results = []
    for hours, interval in test_cases:
        result = test_query_performance(hours, interval)
        if result:
            results.append(result)
        time.sleep(0.5)  # Brief pause between tests
    
    # Summary
    print(f"\n{'='*80}")
    print("PERFORMANCE SUMMARY")
    print(f"{'='*80}")
    print(f"{'Range':<15} {'Interval':<12} {'Points':<12} {'Time':<10} {'Memory':<10} {'Rating'}")
    print(f"{'-'*80}")
    
    for r in results:
        hours_text = f"{r['hours']}h"
        interval_text = f"{r['interval']}s"
        points_text = f"{r['actual_points']:,}"
        time_text = f"{r['query_time']:.2f}s"
        mem_text = f"{r['memory_mb']:.1f}MB"
        
        if r['query_time'] < 1:
            rating = "⚡"
        elif r['query_time'] < 3:
            rating = "✅"
        elif r['query_time'] < 10:
            rating = "⚠️"
        else:
            rating = "❌"
        
        print(f"{hours_text:<15} {interval_text:<12} {points_text:<12} {time_text:<10} {mem_text:<10} {rating}")
    
    print(f"\n✅ Performance test complete!")
    print(f"Total tests: {len(results)}")
    print(f"Average query time: {sum(r['query_time'] for r in results)/len(results):.2f}s")
