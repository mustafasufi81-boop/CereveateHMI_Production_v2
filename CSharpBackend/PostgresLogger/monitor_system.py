import psycopg2
import time

def check_system():
    conn = psycopg2.connect(
        host='localhost',
        database='Cereveate',
        user='cereveate',
        password='cereveate@222'
    )
    cur = conn.cursor()
    
    # Tag catalog
    cur.execute('SELECT COUNT(*) FROM tag_catalog')
    catalog_count = cur.fetchone()[0]
    
    # Unique files in catalog
    cur.execute('SELECT COUNT(DISTINCT last_file) FROM tag_catalog')
    file_count = cur.fetchone()[0]
    
    # Mapped tags
    cur.execute('SELECT COUNT(*) FROM sensor_data WHERE tag_code IS NOT NULL')
    data_count = cur.fetchone()[0]
    
    # Unique tags with data
    cur.execute('SELECT COUNT(DISTINCT tag_code) FROM sensor_data')
    tags_with_data = cur.fetchone()[0]
    
    cur.close()
    conn.close()
    
    print(f"[{time.strftime('%H:%M:%S')}] Catalog: {catalog_count} tags from {file_count} files | Data: {data_count} records for {tags_with_data} tags")

if __name__ == "__main__":
    print("Monitoring PostgresLogger system (Ctrl+C to stop)")
    print("="*80)
    
    try:
        while True:
            check_system()
            time.sleep(10)  # Check every 10 seconds
    except KeyboardInterrupt:
        print("\nStopped monitoring")
