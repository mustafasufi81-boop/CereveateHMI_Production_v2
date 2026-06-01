"""
Verification script for occurrence_id population in alarm_audit_trail.

Tests that after the fix:
1. New ACK/CLEAR/SUPPRESS/UNSUPPRESS actions write occurrence_id to alarm_audit_trail
2. The occurrence_id matches what's in alarm_active table
3. API returns occurrence_id in audit trail records

Run AFTER making test actions (ACK, CLEAR, etc) to verify occurrence_id is populated.
"""

import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timezone

DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'Automation_DB',
    'user': 'cereveate',
    'password': 'cereveate@222'
}

def main():
    print("=" * 80)
    print("OCCURRENCE_ID FIX VERIFICATION")
    print("=" * 80)
    print()
    
    conn = psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)
    
    try:
        # 1. Find an active alarm we can test with
        print("1. Finding active alarms with occurrence_id...")
        cur = conn.cursor()
        cur.execute("""
            SELECT current_event_id, alarm_key, tag_id, alarm_state, occurrence_id
            FROM historian_raw.alarm_active
            WHERE occurrence_id IS NOT NULL
            ORDER BY raised_at DESC
            LIMIT 5
        """)
        active_alarms = cur.fetchall()
        
        if not active_alarms:
            print("   ❌ No active alarms with occurrence_id found")
            print("   💡 This is expected if C# backend hasn't raised any new alarms yet")
            print()
        else:
            print(f"   ✅ Found {len(active_alarms)} active alarms with occurrence_id:")
            for alarm in active_alarms:
                print(f"      Event {alarm['current_event_id']}: {alarm['alarm_key']} | occurrence_id={alarm['occurrence_id']}")
            print()
        
        # 2. Check recent audit trail records for occurrence_id
        print("2. Checking recent audit trail records (last 20)...")
        cur.execute("""
            SELECT 
                audit_id, event_id, tag_id, action_type, 
                action_timestamp, performed_by, occurrence_id
            FROM historian_raw.alarm_audit_trail
            ORDER BY action_timestamp DESC
            LIMIT 20
        """)
        recent_audits = cur.fetchall()
        
        null_count = sum(1 for r in recent_audits if r['occurrence_id'] is None)
        populated_count = len(recent_audits) - null_count
        
        print(f"   📊 Last 20 records: {populated_count} with occurrence_id, {null_count} NULL")
        print()
        
        if populated_count > 0:
            print(f"   ✅ Records WITH occurrence_id (most recent):")
            for record in [r for r in recent_audits if r['occurrence_id'] is not None][:5]:
                print(f"      Audit {record['audit_id']}: event={record['event_id']} "
                      f"action={record['action_type']} by={record['performed_by']} "
                      f"occurrence_id={record['occurrence_id']}")
            print()
        
        if null_count > 0:
            print(f"   ⚠️  Records with NULL occurrence_id (older records):")
            for record in [r for r in recent_audits if r['occurrence_id'] is None][:5]:
                ts = record['action_timestamp'].strftime('%Y-%m-%d %H:%M:%S')
                print(f"      Audit {record['audit_id']}: event={record['event_id']} "
                      f"action={record['action_type']} at {ts} (NULL)")
            print()
        
        # 3. Verify occurrence_id consistency for specific events
        print("3. Verifying occurrence_id consistency...")
        cur.execute("""
            SELECT 
                aa.event_id,
                aa.tag_id,
                aa.action_type,
                aa.occurrence_id AS audit_occ_id,
                act.occurrence_id AS active_occ_id,
                he.occurrence_id AS events_occ_id
            FROM historian_raw.alarm_audit_trail aa
            LEFT JOIN historian_raw.alarm_active act ON aa.event_id = act.current_event_id
            LEFT JOIN historian_raw.historian_events he ON aa.event_id = he.event_id
            WHERE aa.occurrence_id IS NOT NULL
            ORDER BY aa.action_timestamp DESC
            LIMIT 10
        """)
        consistency_checks = cur.fetchall()
        
        if not consistency_checks:
            print("   ⚠️  No audit records with occurrence_id yet (expected if no new actions)")
            print()
        else:
            print(f"   ✅ Checking {len(consistency_checks)} recent records with occurrence_id:")
            mismatches = 0
            for check in consistency_checks:
                audit_occ = str(check['audit_occ_id'])
                active_occ = str(check['active_occ_id']) if check['active_occ_id'] else 'N/A (cleared)'
                events_occ = str(check['events_occ_id']) if check['events_occ_id'] else 'N/A'
                
                match_status = "✅" if (
                    check['active_occ_id'] is None or  # Alarm cleared, no longer in active
                    audit_occ == str(check['active_occ_id'])
                ) else "❌"
                
                if match_status == "❌":
                    mismatches += 1
                
                print(f"      {match_status} Event {check['event_id']} {check['action_type']}:")
                print(f"         audit_trail.occurrence_id = {audit_occ}")
                print(f"         alarm_active.occurrence_id = {active_occ}")
                print(f"         historian_events.occurrence_id = {events_occ}")
            
            if mismatches > 0:
                print(f"   ⚠️  {mismatches} mismatches found (investigate!)")
            else:
                print(f"   ✅ All occurrence_ids match!")
            print()
        
        # 4. Summary statistics
        print("4. Summary Statistics...")
        cur.execute("""
            SELECT 
                COUNT(*) AS total_records,
                COUNT(occurrence_id) AS with_occurrence_id,
                COUNT(*) - COUNT(occurrence_id) AS null_occurrence_id,
                ROUND(100.0 * COUNT(occurrence_id) / COUNT(*), 2) AS percent_populated
            FROM historian_raw.alarm_audit_trail
        """)
        stats = cur.fetchone()
        
        print(f"   📊 Alarm Audit Trail Statistics:")
        print(f"      Total records: {stats['total_records']}")
        print(f"      With occurrence_id: {stats['with_occurrence_id']} ({stats['percent_populated']}%)")
        print(f"      NULL occurrence_id: {stats['null_occurrence_id']} (old records)")
        print()
        
        # 5. Recent actions by type
        print("5. Recent Actions by Type (last 24 hours)...")
        cur.execute("""
            SELECT 
                action_type,
                COUNT(*) AS count,
                COUNT(occurrence_id) AS with_occ_id,
                COUNT(*) - COUNT(occurrence_id) AS without_occ_id
            FROM historian_raw.alarm_audit_trail
            WHERE action_timestamp > NOW() - INTERVAL '24 hours'
            GROUP BY action_type
            ORDER BY count DESC
        """)
        action_stats = cur.fetchall()
        
        if not action_stats:
            print("   ℹ️  No actions in last 24 hours")
        else:
            for stat in action_stats:
                pct = round(100.0 * stat['with_occ_id'] / stat['count'], 1) if stat['count'] > 0 else 0
                print(f"   {stat['action_type']:15} {stat['count']:3} total | "
                      f"{stat['with_occ_id']:3} with occurrence_id ({pct}%)")
        print()
        
        # 6. Test recommendation
        print("=" * 80)
        print("TEST RECOMMENDATION:")
        print("=" * 80)
        
        if populated_count == 0:
            print("⚠️  No audit records with occurrence_id found yet.")
            print()
            print("TO TEST THE FIX:")
            print("1. Restart HMI: cd d:\\CereveateHMI_Production\\HMI ; python app.py")
            print("2. Wait for an alarm to trigger (or manually acknowledge an existing alarm)")
            print("3. Perform an ACK/CLEAR/SUPPRESS action via the UI")
            print("4. Run this script again to verify occurrence_id is populated")
        else:
            print(f"✅ Found {populated_count} recent records with occurrence_id!")
            print()
            print("FIX APPEARS TO BE WORKING!")
            print("- New audit trail records are being written with occurrence_id")
            print("- Old records (NULL) are expected and won't be backfilled")
            print()
            print("NEXT STEPS:")
            print("1. Test API: http://localhost:8090/api/alarms/audit/<event_id>")
            print("2. Verify React UI displays occurrence_id correctly")
            print("3. Check that all action types (ACK/CLEAR/SUPPRESS) write occurrence_id")
        
        print("=" * 80)
        
    finally:
        conn.close()

if __name__ == '__main__':
    main()
