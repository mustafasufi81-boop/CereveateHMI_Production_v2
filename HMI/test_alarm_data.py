"""
Test script to validate alarm data in historian_raw.historian_events table
Run this to check what data exists before finalizing the query
"""
import psycopg2
from psycopg2.extras import RealDictCursor
import json

# Database configuration
db_config = {
    'host': 'localhost',
    'port': 5432,
    'database': 'Historian_data',
    'user': 'postgres',
    'password': 'Database@19c'
}

def test_alarm_data():
    """Test what data exists in the historian_events table"""
    try:
        conn = psycopg2.connect(**db_config, cursor_factory=RealDictCursor)
        cursor = conn.cursor()
        
        print("=" * 80)
        print("ALARM DATA VALIDATION")
        print("=" * 80)
        
        # 1. Total count
        cursor.execute("SELECT COUNT(*) as count FROM historian_raw.historian_events")
        total = cursor.fetchone()['count']
        print(f"\n1. Total events in table: {total}")
        
        # 2. Recent events (last 7 days)
        cursor.execute("""
            SELECT COUNT(*) as count 
            FROM historian_raw.historian_events 
            WHERE time >= NOW() - INTERVAL '7 days'
        """)
        recent = cursor.fetchone()['count']
        print(f"2. Events in last 7 days: {recent}")
        
        # 3. Distinct alarm states
        cursor.execute("SELECT DISTINCT alarm_state FROM historian_raw.historian_events ORDER BY alarm_state")
        states = [row['alarm_state'] for row in cursor.fetchall()]
        print(f"3. Distinct alarm_state values: {states}")
        
        # 4. Distinct severity values
        cursor.execute("SELECT DISTINCT severity FROM historian_raw.historian_events ORDER BY severity")
        severities = [row['severity'] for row in cursor.fetchall()]
        print(f"4. Distinct severity values: {severities}")
        
        # 5. Count by alarm state
        cursor.execute("""
            SELECT 
                alarm_state, 
                COUNT(*) as count 
            FROM historian_raw.historian_events 
            GROUP BY alarm_state 
            ORDER BY count DESC
        """)
        print("\n5. Count by alarm_state:")
        for row in cursor.fetchall():
            print(f"   {row['alarm_state']}: {row['count']}")
        
        # 6. Sample of most recent events
        cursor.execute("""
            SELECT 
                event_id,
                tag_id,
                event_type,
                severity,
                message,
                alarm_state,
                alarm_actual_value,
                time
            FROM historian_raw.historian_events 
            ORDER BY time DESC 
            LIMIT 10
        """)
        print("\n6. Sample of 10 most recent events:")
        print("-" * 80)
        for i, row in enumerate(cursor.fetchall(), 1):
            print(f"\nEvent #{i}:")
            print(f"   ID: {row['event_id']}")
            print(f"   Tag ID: {row['tag_id']}")
            print(f"   Event Type: {row['event_type']}")
            print(f"   Severity: {row['severity']}")
            print(f"   Message: {row['message']}")
            print(f"   Alarm State: {row['alarm_state']}")
            print(f"   Value: {row['alarm_actual_value']}")
            print(f"   Time: {row['time']}")
        
        # 7. Check for events with specific states
        cursor.execute("""
            SELECT 
                COUNT(*) FILTER (WHERE alarm_state IS NULL) as null_state,
                COUNT(*) FILTER (WHERE alarm_state NOT IN ('acknowledged', 'cleared')) as active_state,
                COUNT(*) FILTER (WHERE alarm_state IN ('acknowledged', 'cleared')) as inactive_state
            FROM historian_raw.historian_events
            WHERE time >= NOW() - INTERVAL '7 days'
        """)
        state_counts = cursor.fetchone()
        print("\n7. Event states in last 7 days:")
        print(f"   NULL alarm_state: {state_counts['null_state']}")
        print(f"   Active (not ack/cleared): {state_counts['active_state']}")
        print(f"   Inactive (ack/cleared): {state_counts['inactive_state']}")
        
        cursor.close()
        conn.close()
        
        print("\n" + "=" * 80)
        print("VALIDATION COMPLETE")
        print("=" * 80)
        
    except Exception as e:
        print(f"ERROR: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_alarm_data()
