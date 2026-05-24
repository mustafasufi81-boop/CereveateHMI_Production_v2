import psycopg2
import pandas as pd
from datetime import datetime

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
def get_latest_values():
    conn = connect_db()
    if conn:
        try:
            query = """
                SELECT tag_id, time, value_num, value_text, value_bool, quality 
                FROM historian_raw.historian_latest_value 
                ORDER BY time DESC 
                LIMIT 10
            """
            df = pd.read_sql(query, conn)
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
                ORDER BY time ASC
            """
            df = pd.read_sql(query, conn, params=(tag_id, start_time, end_time))
            print(f"[SUCCESS] Retrieved {len(df)} records for tag {tag_id}")
            conn.close()
            return df
        except Exception as e:
            print(f"[ERROR] Failed to get timeseries data: {e}")
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

# Test connection and database access
if __name__ == "__main__":
    print("=" * 60)
    print("DATABASE CONNECTION TEST")
    print("=" * 60)
    
    # Test connection
    if test_connection():
        print("\n[PASS] Connection test successful")
    else:
        print("\n[FAIL] Connection test failed")
        exit(1)
    
    # Get database statistics
    print("\n" + "=" * 60)
    print("DATABASE STATISTICS")
    print("=" * 60)
    stats = get_database_stats()
    
    if stats:
        print(f"\n[SUMMARY]")
        print(f"  - Total Records: {stats['total_records']}")
        print(f"  - Total Tags: {stats['total_tags']}")
        print(f"  - Enabled Tags: {stats['enabled_tags']}")
        print(f"  - Latest Data: {stats['latest_timestamp']}")
    
    print("\n" + "=" * 60)
    print("ALL TESTS COMPLETED")
    print("=" * 60)
