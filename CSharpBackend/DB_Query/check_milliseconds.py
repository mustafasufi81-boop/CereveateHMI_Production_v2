import psycopg2
from datetime import datetime

DB_CONFIG = {
    'host': '192.168.0.120',
    'port': 5432,
    'database': 'Cereveate',
    'user': 'cereveate',
    'password': 'cereveate@222'
}

try:
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()
    
    # Get recent data with milliseconds
    query = """
    SELECT time, tag_id, value_num, quality
    FROM historian_raw.historian_timeseries
    WHERE tag_id = 'Welding_Voltage_V'
    ORDER BY time DESC
    LIMIT 20
    """
    
    cursor.execute(query)
    rows = cursor.fetchall()
    
    print("\n" + "="*100)
    print("DATABASE TIMESTAMP VALUES (with milliseconds)")
    print("="*100)
    
    for i, row in enumerate(rows, 1):
        timestamp = row[0]
        tag_id = row[1]
        value = row[2]
        quality = row[3]
        
        # Show full timestamp with microseconds
        print(f"{i}. Time: {timestamp} (Type: {type(timestamp).__name__})")
        print(f"   Full: {timestamp.isoformat()}")
        print(f"   Tag: {tag_id}, Value: {value}, Quality: {quality}")
        print(f"   Milliseconds: {timestamp.microsecond // 1000}")
        print()
    
    cursor.close()
    conn.close()
    
except Exception as e:
    print(f"Error: {e}")
