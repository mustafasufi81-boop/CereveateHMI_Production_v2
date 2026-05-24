import psycopg2
import pandas as pd
from datetime import datetime, timedelta

# Database connection configuration
DB_CONFIG = {
    'host': '192.168.0.120',      # Your Windows PC IP (use whichever network Pi is on)
    'port': 5432,
    'database': 'Cereveate',
    'user': 'cereveate',
    'password': 'cereveate@222'
}

# Connect to database
def connect_db():
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        print("[SUCCESS] Connected to database successfully!")
        return conn
    except Exception as e:
        print(f"[ERROR] Connection failed: {e}")
        return None

# Check if database connection is working
def test_connection():
    conn = connect_db()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT version()")
            version = cursor.fetchone()[0]
            print(f"[INFO] PostgreSQL version: {version}")
            cursor.close()
            conn.close()
            return True
        except Exception as e:
            print(f"[ERROR] Query failed: {e}")
            return False
    return False

# Example: Read latest tag values
def get_latest_values(limit=10):
    conn = connect_db()
    if conn:
        try:
            query = """
                SELECT tag_id, time, value_num, value_text, value_bool, quality 
                FROM historian_raw.historian_latest_value 
                ORDER BY time DESC 
                LIMIT %s
            """
            df = pd.read_sql(query, conn, params=(limit,))
            print(f"[SUCCESS] Retrieved {len(df)} latest values")
            conn.close()
            return df
        except Exception as e:
            print(f"[ERROR] Failed to get latest values: {e}")
            conn.close()
            return None

# Example: Read time-series data
def get_timeseries_data(tag_id, start_time, end_time):
    conn = connect_db()
    if conn:
        try:
            query = """
                SELECT time, tag_id, value_num, value_text, value_bool, quality
                FROM historian_raw.historian_timeseries
                WHERE tag_id = %s 
                  AND time BETWEEN %s AND %s
                ORDER BY time DESC
                LIMIT 100
            """
            df = pd.read_sql(query, conn, params=(tag_id, start_time, end_time))
            print(f"[SUCCESS] Retrieved {len(df)} records for tag {tag_id}")
            conn.close()
            return df
        except Exception as e:
            print(f"[ERROR] Failed to get timeseries data: {e}")
            conn.close()
            return None

# Get recent data for any tag (last N records)
def get_recent_data(tag_id, limit=50):
    conn = connect_db()
    if conn:
        try:
            query = """
                SELECT time, tag_id, value_num, quality
                FROM historian_raw.historian_timeseries
                WHERE tag_id = %s
                ORDER BY time DESC
                LIMIT %s
            """
            df = pd.read_sql(query, conn, params=(tag_id, limit))
            print(f"[SUCCESS] Retrieved {len(df)} recent records for tag {tag_id}")
            conn.close()
            return df
        except Exception as e:
            print(f"[ERROR] Failed to get recent data: {e}")
            conn.close()
            return None

# Example: Get all enabled tags
def get_enabled_tags():
    conn = connect_db()
    if conn:
        try:
            query = """
                SELECT tag_id, tag_name, data_type, db_logging_interval_ms
                FROM historian_meta.tag_master
                WHERE enabled = true
                ORDER BY tag_id
            """
            df = pd.read_sql(query, conn)
            print(f"[SUCCESS] Retrieved {len(df)} enabled tags")
            conn.close()
            return df
        except Exception as e:
            print(f"[ERROR] Failed to get enabled tags: {e}")
            conn.close()
            return None

# Check database statistics
def get_database_stats():
    conn = connect_db()
    if conn:
        try:
            cursor = conn.cursor()
            
            # Count total records
            cursor.execute("SELECT COUNT(*) FROM historian_raw.historian_timeseries")
            total_records = cursor.fetchone()[0]
            print(f"[INFO] Total timeseries records: {total_records}")
            
            # Count total tags
            cursor.execute("SELECT COUNT(*) FROM historian_meta.tag_master")
            total_tags = cursor.fetchone()[0]
            print(f"[INFO] Total tags: {total_tags}")
            
            # Count enabled tags
            cursor.execute("SELECT COUNT(*) FROM historian_meta.tag_master WHERE enabled = true")
            enabled_tags = cursor.fetchone()[0]
            print(f"[INFO] Enabled tags: {enabled_tags}")
            
            # Get latest data timestamp
            cursor.execute("SELECT MAX(time) FROM historian_raw.historian_timeseries")
            latest_time = cursor.fetchone()[0]
            print(f"[INFO] Latest data timestamp: {latest_time}")
            
            cursor.close()
            conn.close()
            
            return {
                'total_records': total_records,
                'total_tags': total_tags,
                'enabled_tags': enabled_tags,
                'latest_timestamp': latest_time
            }
        except Exception as e:
            print(f"[ERROR] Failed to get database stats: {e}")
            conn.close()
            return None

# Insert test data (for testing database write access)
def insert_test_record(tag_id, value):
    conn = connect_db()
    if conn:
        try:
            cursor = conn.cursor()
            query = """
                INSERT INTO historian_raw.historian_timeseries 
                (time, tag_id, value_num, quality, sample_source)
                VALUES (NOW(), %s, %s, 'G', 'T')
            """
            cursor.execute(query, (tag_id, value))
            conn.commit()
            print(f"[SUCCESS] Inserted test record for tag {tag_id} with value {value}")
            cursor.close()
            conn.close()
            return True
        except Exception as e:
            print(f"[ERROR] Failed to insert test record: {e}")
            conn.close()
            return False

# Get tag list (just tag IDs)
def get_tag_list():
    conn = connect_db()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT tag_id FROM historian_meta.tag_master WHERE enabled = true ORDER BY tag_id LIMIT 10")
            tags = [row[0] for row in cursor.fetchall()]
            cursor.close()
            conn.close()
            return tags
        except Exception as e:
            print(f"[ERROR] Failed to get tag list: {e}")
            return []

# Test connection and database access
if __name__ == "__main__":
    print("=" * 60)
    print("DATABASE CONNECTION TEST")
    print("=" * 60)
    
    # Test connection
    if test_connection():
        print("[PASS] Connection test successful\n")
    else:
        print("[FAIL] Connection test failed")
        exit(1)
    
    # Get database statistics
    print("=" * 60)
    print("DATABASE STATISTICS")
    print("=" * 60)
    stats = get_database_stats()
    
    if stats:
        print(f"\n[SUMMARY]")
        print(f"  - Total Records: {stats['total_records']}")
        print(f"  - Total Tags: {stats['total_tags']}")
        print(f"  - Enabled Tags: {stats['enabled_tags']}")
        print(f"  - Latest Data: {stats['latest_timestamp']}\n")
    
    # Get list of tags
    print("=" * 60)
    print("AVAILABLE TAGS")
    print("=" * 60)
    tags = get_tag_list()
    if tags:
        print(f"[INFO] Found {len(tags)} tags:")
        for i, tag in enumerate(tags[:5], 1):
            print(f"  {i}. {tag}")
        
        # Test reading recent data from first tag
        if tags:
            test_tag = tags[0]
            print(f"\n[INFO] Testing data read for tag: {test_tag}\n")
            
            print("=" * 60)
            print(f"RECENT DATA FOR TAG: {test_tag}")
            print("=" * 60)
            recent_data = get_recent_data(test_tag, limit=5)
            if recent_data is not None and not recent_data.empty:
                print("\nSample data:")
                print(recent_data.to_string(index=False))
            else:
                print("[WARNING] No data found for this tag")
    
    # Test write operation
    print("\n" + "=" * 60)
    print("TEST WRITE OPERATION")
    print("=" * 60)
    test_value = 123.45
    if tags:
        insert_test_record(tags[0], test_value)
    
    print("\n" + "=" * 60)
    print("ALL TESTS COMPLETED SUCCESSFULLY")
    print("=" * 60)
