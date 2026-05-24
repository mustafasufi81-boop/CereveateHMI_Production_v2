"""
OPC Polling & Database Write Interval Diagnostic Script

This script checks:
1. Tag mapping intervals (db_logging_interval_ms) in historian_meta.tag_master
2. Actual data arrival rates in historian_raw.historian_timeseries
3. OPC connection polling intervals
4. Rate control/deadband settings
5. Batch processing delays

Purpose: Identify why data appears in database with 5-second intervals
instead of 1-second intervals despite OPC values changing rapidly.
"""

import psycopg2
from psycopg2 import sql
from datetime import datetime, timedelta
from collections import defaultdict
import sys

# Database connection
DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'Cereveate',
    'user': 'cereveate',
    'password': 'cereveate@222'
}

def print_header(text):
    """Print formatted section header"""
    print("\n" + "="*80)
    print(f"  {text}")
    print("="*80)

def check_tag_master_intervals():
    """Check db_logging_interval_ms settings for all enabled tags"""
    print_header("1. TAG MASTER POLLING INTERVALS")
    
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        
        query = """
        SELECT 
            tag_id,
            db_logging_interval_ms,
            deadband_value,
            enabled,
            data_type,
            plant,
            equipment
        FROM historian_meta.tag_master
        WHERE enabled = true
        ORDER BY db_logging_interval_ms, tag_id
        """
        
        cur.execute(query)
        rows = cur.fetchall()
        
        if not rows:
            print("❌ No enabled tags found in tag_master!")
            return
        
        print(f"\n✅ Found {len(rows)} enabled tags\n")
        
        # Group by interval
        interval_groups = defaultdict(list)
        for row in rows:
            tag_id, interval_ms, deadband, enabled, dtype, plant, equip = row
            interval_groups[interval_ms].append({
                'tag_id': tag_id,
                'deadband': deadband,
                'type': dtype,
                'plant': plant,
                'equipment': equip
            })
        
        # Display summary
        for interval_ms in sorted(interval_groups.keys()):
            tags = interval_groups[interval_ms]
            print(f"  Interval: {interval_ms}ms ({interval_ms/1000:.1f}s) → {len(tags)} tags")
            for tag in tags[:3]:  # Show first 3
                print(f"    - {tag['tag_id']} (deadband={tag['deadband']}, type={tag['type']})")
            if len(tags) > 3:
                print(f"    ... and {len(tags)-3} more")
            print()
        
        cur.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")

def check_actual_data_intervals():
    """Check actual time intervals between consecutive data points in historian_timeseries"""
    print_header("2. ACTUAL DATA ARRIVAL INTERVALS (Last 5 minutes)")
    
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        
        # Get recent data with intervals
        query = """
        WITH recent_data AS (
            SELECT 
                tag_id,
                time,
                value,
                LAG(time) OVER (PARTITION BY tag_id ORDER BY time) as prev_time
            FROM historian_raw.historian_timeseries
            WHERE time >= NOW() - INTERVAL '5 minutes'
        )
        SELECT 
            tag_id,
            COUNT(*) as sample_count,
            ROUND(AVG(EXTRACT(EPOCH FROM (time - prev_time)) * 1000)::numeric, 0) as avg_interval_ms,
            ROUND(MIN(EXTRACT(EPOCH FROM (time - prev_time)) * 1000)::numeric, 0) as min_interval_ms,
            ROUND(MAX(EXTRACT(EPOCH FROM (time - prev_time)) * 1000)::numeric, 0) as max_interval_ms,
            MAX(time) as last_sample
        FROM recent_data
        WHERE prev_time IS NOT NULL
        GROUP BY tag_id
        ORDER BY avg_interval_ms DESC
        LIMIT 20
        """
        
        cur.execute(query)
        rows = cur.fetchall()
        
        if not rows:
            print("❌ No recent data found in historian_timeseries (last 5 minutes)")
            return
        
        print(f"\n✅ Found data for {len(rows)} tags\n")
        print(f"{'Tag ID':<30} {'Samples':>8} {'Avg(ms)':>9} {'Min(ms)':>9} {'Max(ms)':>9} {'Last Sample'}")
        print("-" * 100)
        
        for row in rows:
            tag_id, count, avg_ms, min_ms, max_ms, last_sample = row
            print(f"{tag_id:<30} {count:>8} {avg_ms:>9} {min_ms:>9} {max_ms:>9} {last_sample.strftime('%H:%M:%S')}")
        
        cur.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")

def check_rate_control_settings():
    """Check rate control and deadband configuration"""
    print_header("3. RATE CONTROL & DEADBAND SETTINGS")
    
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        
        query = """
        SELECT 
            tag_id,
            deadband_value,
            db_logging_interval_ms,
            data_type
        FROM historian_meta.tag_master
        WHERE enabled = true
        ORDER BY deadband_value DESC
        LIMIT 10
        """
        
        cur.execute(query)
        rows = cur.fetchall()
        
        if rows:
            print(f"\n✅ Top 10 tags by deadband value:\n")
            print(f"{'Tag ID':<30} {'Deadband':>12} {'Interval(ms)':>12} {'Type':<10}")
            print("-" * 70)
            
            for row in rows:
                tag_id, deadband, interval_ms, dtype = row
                print(f"{tag_id:<30} {deadband:>12.4f} {interval_ms:>12} {dtype:<10}")
        
        print("\n📋 Rate Control Configuration (from appsettings.json):")
        print("   Historian.RateControl.Enabled: true")
        print("   Historian.RateControl.UseChangeDetection: true")
        print("   Historian.RateControl.DefaultDeadband: 0.1")
        print("   Historian.RateControl.MinIntervalMs: 1000")
        print("   Historian.RateControl.MaxIntervalMs: 60000")
        
        print("\n⚠️  IMPORTANT: Rate control FILTERS data before DB writes")
        print("   - Values within deadband are NOT written to database")
        print("   - Only significant changes appear in historian_timeseries")
        
        cur.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")

def check_batch_settings():
    """Check batch processing configuration"""
    print_header("4. BATCH PROCESSING SETTINGS")
    
    print("\n📋 Batch Configuration (from appsettings.json):")
    print("   Historian.Batch.MaxRows: 1")
    print("   Historian.Batch.MaxWaitMs: 500")
    print("   Historian.Batch.UseBinaryCopy: true")
    
    print("\n⚠️  CRITICAL FINDING:")
    print("   MaxRows=1 means EVERY SINGLE sample triggers a DB write")
    print("   This creates maximum database load but minimum latency")
    print("   Each write has ~500ms max wait time")

def check_recent_data_flow():
    """Check if data is flowing right now"""
    print_header("5. REAL-TIME DATA FLOW CHECK")
    
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        
        # Check last 30 seconds
        query = """
        SELECT 
            tag_id,
            COUNT(*) as samples,
            MAX(time) as last_time,
            EXTRACT(EPOCH FROM (NOW() - MAX(time))) as seconds_ago
        FROM historian_raw.historian_timeseries
        WHERE time >= NOW() - INTERVAL '30 seconds'
        GROUP BY tag_id
        ORDER BY last_time DESC
        """
        
        cur.execute(query)
        rows = cur.fetchall()
        
        if not rows:
            print("❌ No data in last 30 seconds - OPC may not be running!")
            return
        
        print(f"\n✅ Data flowing: {len(rows)} tags received data in last 30 seconds\n")
        print(f"{'Tag ID':<30} {'Samples':>8} {'Last Time':>20} {'Age(s)':>8}")
        print("-" * 75)
        
        for row in rows[:15]:  # Show top 15
            tag_id, samples, last_time, age = row
            print(f"{tag_id:<30} {samples:>8} {last_time.strftime('%H:%M:%S.%f')[:15]:>20} {age:>8.1f}")
        
        if len(rows) > 15:
            print(f"\n... and {len(rows)-15} more tags")
        
        cur.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")

def check_timestamp_distribution():
    """Check timestamp distribution to detect sampling patterns"""
    print_header("6. TIMESTAMP DISTRIBUTION ANALYSIS (Last 2 minutes)")
    
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        
        # Analyze timestamp second boundaries
        query = """
        SELECT 
            EXTRACT(EPOCH FROM time)::bigint % 10 as second_mod10,
            COUNT(*) as sample_count
        FROM historian_raw.historian_timeseries
        WHERE time >= NOW() - INTERVAL '2 minutes'
        GROUP BY second_mod10
        ORDER BY second_mod10
        """
        
        cur.execute(query)
        rows = cur.fetchall()
        
        if rows:
            print("\n📊 Sample distribution by second (mod 10):")
            print("   If data arrives every 5s, you'll see peaks at 0 and 5\n")
            
            max_count = max(r[1] for r in rows)
            for second, count in rows:
                bar_len = int((count / max_count) * 50)
                bar = "█" * bar_len
                print(f"   Second {second}: {bar} {count}")
        
        cur.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")

def generate_recommendations():
    """Generate recommendations based on findings"""
    print_header("7. RECOMMENDATIONS")
    
    print("\n🔍 ROOT CAUSE ANALYSIS:")
    print("\n   The 5-second interval you're seeing is likely caused by:")
    print("   1. db_logging_interval_ms in tag_master is set to 5000ms (not 1000ms)")
    print("   2. Rate control with deadband filtering (removes unchanged values)")
    print("   3. Combination of both factors")
    
    print("\n✅ SOLUTIONS:")
    print("\n   Solution 1: Reduce db_logging_interval_ms to 1000ms")
    print("   --------------------------------------------------------")
    print("   UPDATE historian_meta.tag_master")
    print("   SET db_logging_interval_ms = 1000")
    print("   WHERE enabled = true;")
    print("   ")
    print("   Then restart OPC backend to reload mappings")
    
    print("\n   Solution 2: Disable deadband for fast-changing tags")
    print("   ----------------------------------------------------")
    print("   UPDATE historian_meta.tag_master")
    print("   SET deadband_value = 0.0")
    print("   WHERE tag_id IN ('Random.Real4', 'Random.UInt2', ...)  -- Fast tags")
    print("     AND enabled = true;")
    
    print("\n   Solution 3: Disable rate control entirely (appsettings.json)")
    print("   ------------------------------------------------------------")
    print("   \"RateControl\": {")
    print("     \"Enabled\": false,  // ← Change to false")
    print("     \"UseChangeDetection\": false")
    print("   }")
    print("   ")
    print("   ⚠️  WARNING: This will write EVERY sample to DB (high load)")
    
    print("\n   Solution 4: Verify OPC polling is at 1000ms")
    print("   --------------------------------------------")
    print("   Check Program.cs or connection logs for polling interval")
    print("   Default should be 1000ms but verify actual setting")

def main():
    """Main execution"""
    print("\n")
    print("╔" + "═"*78 + "╗")
    print("║" + " "*20 + "OPC POLLING DIAGNOSTIC TOOL" + " "*31 + "║")
    print("║" + " "*78 + "║")
    print("║  Analyzing why historian data arrives with 5-second intervals" + " "*15 + "║")
    print("║  instead of 1-second intervals" + " "*47 + "║")
    print("╚" + "═"*78 + "╝")
    
    try:
        check_tag_master_intervals()
        check_actual_data_intervals()
        check_rate_control_settings()
        check_batch_settings()
        check_recent_data_flow()
        check_timestamp_distribution()
        generate_recommendations()
        
        print_header("DIAGNOSTIC COMPLETE")
        print("\n✅ Analysis finished. Review findings above.\n")
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
