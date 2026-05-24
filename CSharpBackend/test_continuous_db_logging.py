"""
Continuous Database Logging Test at ~100ms (OPC change rate)
Demonstrates system power: reading OPC + writing to PostgreSQL historian
"""
import requests
import time
import psycopg2
from datetime import datetime
import json

# Load config
with open('appsettings.json', 'r') as f:
    config = json.load(f)

# Database connection
DB_CONFIG = config['Historian']['Database']['ConnectionString']
API_BASE = "http://localhost:5001"
TAG_NAME = "Random.Int2"

def parse_connection_string(conn_str):
    """Parse PostgreSQL connection string"""
    params = {}
    for part in conn_str.split(';'):
        if '=' in part:
            key, value = part.split('=', 1)
            params[key.strip().lower()] = value.strip()
    return params

def get_db_connection():
    """Create PostgreSQL connection"""
    params = parse_connection_string(DB_CONFIG)
    return psycopg2.connect(
        host=params.get('host', 'localhost'),
        port=int(params.get('port', 5432)),
        database=params.get('database', 'opc_historian'),
        user=params.get('username', 'postgres'),
        password=params.get('password', '')
    )

def get_tag_value():
    """Get current tag value from OPC pool"""
    try:
        response = requests.get(f"{API_BASE}/api/opc/values", timeout=2)
        if response.status_code == 200:
            data = response.json()
            tags = data.get('tags', [])
            
            for tag in tags:
                tag_id = tag.get('tagId') or tag.get('TagId')
                if tag_id == TAG_NAME:
                    return {
                        'value': tag.get('value') or tag.get('Value'),
                        'quality': tag.get('quality') or tag.get('Quality'),
                        'timestamp': tag.get('timestamp') or tag.get('Timestamp')
                    }
    except Exception as e:
        print(f"API Error: {e}")
    return None

def log_to_database(conn, tag_data, read_time_ms):
    """Write tag value to historian database"""
    try:
        cursor = conn.cursor()
        
        # Insert into historian_raw.historian_timeseries (correct schema)
        insert_sql = """
        INSERT INTO historian_raw.historian_timeseries 
        (time, tag_id, value_num, quality, sample_source, mapping_version)
        VALUES (NOW(), %s, %s, %s, %s, 1)
        """
        
        # Quality: 'G' for GOOD, 'B' for BAD
        quality_code = 'G' if tag_data['quality'] == 'GOOD' else 'B'
        
        cursor.execute(insert_sql, (
            TAG_NAME,
            float(tag_data['value']),
            quality_code,
            'OPC_DA'
        ))
        
        conn.commit()
        cursor.close()
        return True
        
    except Exception as e:
        print(f"DB Error: {e}")
        conn.rollback()
        return False

def continuous_logging_test(duration_seconds=60, target_interval_ms=111):
    """
    Continuous test: read OPC at actual change rate (~111ms), log changes to database
    Shows system power under sustained operation
    """
    print(f"{'='*80}")
    print(f"CONTINUOUS DATABASE LOGGING TEST")
    print(f"Tag: {TAG_NAME}")
    print(f"Target Interval: {target_interval_ms}ms (actual OPC change rate)")
    print(f"Duration: {duration_seconds}s")
    print(f"Database: PostgreSQL historian_raw.historian_timeseries")
    print(f"{'='*80}\n")
    
    # Connect to database
    try:
        conn = get_db_connection()
        print("✅ Database connected")
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return
    
    print(f"\n{'Time':<8} {'Reads':<8} {'Changes':<8} {'DB Writes':<10} {'Avg Read':<10} {'Status'}")
    print(f"{'-'*80}")
    
    start_time = time.time()
    last_value = None
    
    total_reads = 0
    total_changes = 0
    total_db_writes = 0
    total_read_time = 0
    
    try:
        while time.time() - start_time < duration_seconds:
            loop_start = time.time()
            
            # Read OPC value
            read_start = time.time()
            tag_data = get_tag_value()
            read_time_ms = (time.time() - read_start) * 1000
            
            total_reads += 1
            total_read_time += read_time_ms
            
            if tag_data:
                current_value = tag_data['value']
                
                # Check if value changed
                if last_value is not None and current_value != last_value:
                    total_changes += 1
                    
                    # Write to database
                    if log_to_database(conn, tag_data, read_time_ms):
                        total_db_writes += 1
                        status = "✓ DB WRITE"
                    else:
                        status = "✗ DB FAIL"
                else:
                    status = "no change"
                
                last_value = current_value
                
                # Print stats every second
                elapsed = time.time() - start_time
                if total_reads % 10 == 0:
                    avg_read = total_read_time / total_reads
                    print(f"{elapsed:>7.1f}s {total_reads:<8} {total_changes:<8} {total_db_writes:<10} {avg_read:<9.2f}ms {status}")
            
            # Sleep to maintain target interval
            elapsed_loop = (time.time() - loop_start) * 1000
            sleep_time = max(0, (target_interval_ms - elapsed_loop) / 1000)
            time.sleep(sleep_time)
            
    except KeyboardInterrupt:
        print("\n\n⏸️  Test interrupted by user")
    finally:
        conn.close()
    
    # Final statistics
    elapsed_total = time.time() - start_time
    
    print(f"\n{'='*80}")
    print(f"FINAL RESULTS - {elapsed_total:.1f}s continuous operation")
    print(f"{'='*80}")
    print(f"Total OPC Reads:       {total_reads}")
    print(f"Value Changes:         {total_changes}")
    print(f"Database Writes:       {total_db_writes}")
    print(f"Write Success Rate:    {total_db_writes/max(total_changes,1)*100:.1f}%")
    print(f"")
    print(f"Average Read Time:     {total_read_time/total_reads:.2f}ms")
    print(f"Reads per Second:      {total_reads/elapsed_total:.1f}")
    print(f"DB Writes per Second:  {total_db_writes/elapsed_total:.1f}")
    print(f"")
    print(f"Average Change Rate:   {elapsed_total/max(total_changes,1)*1000:.1f}ms between changes")
    print(f"{'='*80}\n")
    
    # Verify database writes
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT COUNT(*), MIN(time), MAX(time)
            FROM historian_raw.historian_timeseries
            WHERE tag_id = %s
            AND sample_source = 'OPC_DA'
            AND time >= NOW() - INTERVAL '5 minutes'
        """, (TAG_NAME,))
        
        count, min_ts, max_ts = cursor.fetchone()
        
        print(f"✅ DATABASE VERIFICATION:")
        print(f"   Records written: {count}")
        print(f"   Time range: {min_ts} to {max_ts}")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"⚠️  Verification error: {e}")

if __name__ == "__main__":
    print("\n🚀 Starting Continuous Database Logging Test...\n")
    print("This test demonstrates:")
    print("  • Fast OPC polling at actual change rate (~111ms)")
    print("  • Real-time change detection")
    print("  • High-frequency database writes")
    print("  • Sustained operation under load\n")
    
    duration = input("Enter test duration in seconds (default 60): ").strip()
    duration = int(duration) if duration.isdigit() else 60
    
    print(f"\n⏱️  Running for {duration} seconds...")
    print("Press Ctrl+C to stop early\n")
    
    continuous_logging_test(duration_seconds=duration, target_interval_ms=111)
    
    print("\n✅ Test complete!")
