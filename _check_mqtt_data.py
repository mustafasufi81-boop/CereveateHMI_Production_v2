"""Check what data sources are writing to historian_timeseries"""
import psycopg2

try:
    conn = psycopg2.connect(
        dbname='Automation_DB',
        user='cereveate',
        password='cereveate@222',
        host='localhost'
    )
    cur = conn.cursor()
    
    # Check sample_source distribution
    print("=" * 80)
    print("SAMPLE SOURCE DISTRIBUTION")
    print("=" * 80)
    cur.execute("""
        SELECT 
            sample_source, 
            COUNT(*) as record_count,
            MIN(time) as first_sample,
            MAX(time) as last_sample,
            COUNT(DISTINCT tag_id) as unique_tags
        FROM historian_raw.historian_timeseries 
        GROUP BY sample_source 
        ORDER BY sample_source
    """)
    
    print(f"{'Source':<15} | {'Count':>10} | {'Unique Tags':>12} | {'First Sample':<25} | {'Last Sample':<25}")
    print("-" * 110)
    
    for row in cur.fetchall():
        print(f"{row[0]:<15} | {row[1]:>10,} | {row[2]:>12} | {str(row[3]):<25} | {str(row[4]):<25}")
    
    # Check recent MQTT vs OPC/PLC samples
    print("\n" + "=" * 80)
    print("RECENT SAMPLES (Last 10 per source)")
    print("=" * 80)
    
    for source in ['MQTT', 'OPC', 'PLC']:
        cur.execute("""
            SELECT tag_id, time, value_num, quality 
            FROM historian_raw.historian_timeseries 
            WHERE sample_source = %s 
            ORDER BY time DESC 
            LIMIT 10
        """, (source,))
        
        rows = cur.fetchall()
        if rows:
            print(f"\n{source} Source ({len(rows)} samples):")
            print(f"  {'Tag ID':<30} | {'Timestamp':<25} | {'Value':>10} | {'Quality'}")
            print("  " + "-" * 85)
            for row in rows[:5]:  # Show first 5
                print(f"  {row[0]:<30} | {str(row[1]):<25} | {row[2] if row[2] is not None else 'NULL':>10} | {row[3]}")
        else:
            print(f"\n{source} Source: No data found")
    
    conn.close()
    print("\n" + "=" * 80)
    print("CONCLUSION: Check if MQTT source has recent timestamps")
    print("=" * 80)

except Exception as e:
    print(f"Error: {e}")
