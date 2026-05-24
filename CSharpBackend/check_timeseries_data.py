#!/usr/bin/env python3
# Check PLC data in historian_timeseries table
# Author: Cereveate Tech

import psycopg2
from datetime import datetime, timedelta

DB_CONFIG = {
    'host': '192.168.0.120',
    'port': 5432,
    'database': 'Cereveate',
    'user': 'cereveate',
    'password': 'cereveate@222',
    'sslmode': 'disable'
}

def check_timeseries_data():
    """Query historian_timeseries table for PLC data"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        
        print("=" * 80)
        print("HISTORIAN TIMESERIES TABLE - PLC DATA VERIFICATION")
        print("=" * 80)
        
        # 1. Total record count
        cur.execute("""
            SELECT COUNT(*) 
            FROM historian_raw.historian_timeseries
            WHERE sample_source = 'P'
        """)
        total_count = cur.fetchone()[0]
        print(f"\n1. TOTAL PLC RECORDS: {total_count:,}")
        
        # 2. Unique tags from PLC
        cur.execute("""
            SELECT COUNT(DISTINCT tag_id) 
            FROM historian_raw.historian_timeseries
            WHERE sample_source = 'P'
        """)
        unique_tags = cur.fetchone()[0]
        print(f"2. UNIQUE PLC TAGS: {unique_tags}")
        
        # 3. Latest 10 records
        print("\n3. LATEST 10 RECORDS:")
        print("-" * 80)
        cur.execute("""
            SELECT 
                time,
                tag_id,
                value_num,
                value_text,
                value_bool,
                quality,
                sample_source
            FROM historian_raw.historian_timeseries
            WHERE sample_source = 'P'
            ORDER BY time DESC
            LIMIT 10
        """)
        
        print(f"{'Time':<20} {'Tag ID':<30} {'Num':<12} {'Bool':<8} {'Quality':<8}")
        print("-" * 80)
        for row in cur.fetchall():
            time_str = row[0].strftime('%Y-%m-%d %H:%M:%S') if row[0] else 'NULL'
            tag_id = row[1] or 'NULL'
            value_num = f"{row[2]:.3f}" if row[2] is not None else 'NULL'
            value_bool = str(row[4]) if row[4] is not None else 'NULL'
            quality = row[5] or 'NULL'
            print(f"{time_str:<20} {tag_id:<30} {value_num:<12} {value_bool:<8} {quality:<8}")
        
        # 4. Records by tag
        print("\n4. RECORD COUNT BY TAG (Top 20):")
        print("-" * 80)
        cur.execute("""
            SELECT 
                tag_id,
                COUNT(*) as record_count,
                MIN(time) as first_record,
                MAX(time) as last_record
            FROM historian_raw.historian_timeseries
            WHERE sample_source = 'P'
            GROUP BY tag_id
            ORDER BY record_count DESC
            LIMIT 20
        """)
        
        print(f"{'Tag ID':<40} {'Count':<10} {'First Record':<20} {'Last Record':<20}")
        print("-" * 80)
        for row in cur.fetchall():
            tag_id = row[0]
            count = row[1]
            first_time = row[2].strftime('%Y-%m-%d %H:%M:%S') if row[2] else 'NULL'
            last_time = row[3].strftime('%Y-%m-%d %H:%M:%S') if row[3] else 'NULL'
            print(f"{tag_id:<40} {count:<10} {first_time:<20} {last_time:<20}")
        
        # 5. Recent activity (last 5 minutes)
        print("\n5. ACTIVITY IN LAST 5 MINUTES:")
        print("-" * 80)
        five_min_ago = datetime.utcnow() - timedelta(minutes=5)
        cur.execute("""
            SELECT 
                COUNT(*) as records,
                COUNT(DISTINCT tag_id) as unique_tags,
                MIN(time) as earliest,
                MAX(time) as latest
            FROM historian_raw.historian_timeseries
            WHERE sample_source = 'P'
                AND time >= %s
        """, (five_min_ago,))
        
        row = cur.fetchone()
        if row and row[0] > 0:
            print(f"Records: {row[0]:,}")
            print(f"Unique Tags: {row[1]}")
            print(f"Earliest: {row[2].strftime('%Y-%m-%d %H:%M:%S') if row[2] else 'NULL'}")
            print(f"Latest: {row[3].strftime('%Y-%m-%d %H:%M:%S') if row[3] else 'NULL'}")
        else:
            print("No records in last 5 minutes")
        
        # 6. Data type distribution
        print("\n6. DATA TYPE DISTRIBUTION:")
        print("-" * 80)
        cur.execute("""
            SELECT 
                CASE 
                    WHEN value_bool IS NOT NULL THEN 'BOOLEAN'
                    WHEN value_num IS NOT NULL THEN 'NUMERIC'
                    WHEN value_text IS NOT NULL THEN 'TEXT'
                    ELSE 'NULL'
                END as data_type,
                COUNT(*) as count
            FROM historian_raw.historian_timeseries
            WHERE sample_source = 'P'
            GROUP BY data_type
            ORDER BY count DESC
        """)
        
        print(f"{'Data Type':<15} {'Count':<15} {'Percentage':<15}")
        print("-" * 80)
        for row in cur.fetchall():
            data_type = row[0]
            count = row[1]
            percentage = (count / total_count * 100) if total_count > 0 else 0
            print(f"{data_type:<15} {count:<15,} {percentage:>6.2f}%")
        
        # 7. Sample of actual tag values
        print("\n7. SAMPLE TAG VALUES (Numeric Tags):")
        print("-" * 80)
        cur.execute("""
            SELECT 
                tag_id,
                value_num,
                time
            FROM historian_raw.historian_timeseries
            WHERE sample_source = 'P'
                AND value_num IS NOT NULL
            ORDER BY time DESC
            LIMIT 10
        """)
        
        print(f"{'Tag ID':<40} {'Value':<15} {'Time':<20}")
        print("-" * 80)
        for row in cur.fetchall():
            tag_id = row[0]
            value = f"{row[1]:.3f}" if row[1] is not None else 'NULL'
            time_str = row[2].strftime('%Y-%m-%d %H:%M:%S') if row[2] else 'NULL'
            print(f"{tag_id:<40} {value:<15} {time_str:<20}")
        
        print("\n" + "=" * 80)
        print("✓ QUERY COMPLETED SUCCESSFULLY")
        print("=" * 80)
        
        cur.close()
        conn.close()
        
    except Exception as e:
        print(f"\n[ERROR] Database query failed: {e}")

if __name__ == "__main__":
    check_timeseries_data()
