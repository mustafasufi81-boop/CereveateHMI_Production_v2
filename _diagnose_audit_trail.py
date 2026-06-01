"""
Simple Diagnostic: Check actual audit trail data for VYAN1101G
Understand why 12 ACKs + 4 CLEARs are showing up
"""
import psycopg2

def diagnose_audit_data():
    try:
        conn = psycopg2.connect(
            dbname='Automation_DB',
            user='cereveate',
            password='cereveate@222',
            host='localhost',
            port=5432
        )
        cur = conn.cursor()
        
        print("=" * 80)
        print("DIAGNOSTIC: Audit Trail Data Analysis")
        print("=" * 80)
        
        # 1. Check historian_events for VYAN1101G
        print("\n1️⃣  Checking historian_events for VYAN1101G...")
        print("-" * 80)
        cur.execute("""
            SELECT event_id, occurrence_id, time, alarm_state, alarm_actual_value 
            FROM historian_raw.historian_events 
            WHERE tag_id = 'VYAN1101G' 
            ORDER BY time DESC 
            LIMIT 5
        """)
        events = cur.fetchall()
        
        print(f"Found {len(events)} recent events:")
        for e in events:
            event_id, occ_id, ts, state, val = e
            occ_short = str(occ_id)[:13] if occ_id else 'None'
            print(f"  Event {event_id} | Occ: {occ_short}... | {ts} | {state} | Val: {val:.2f}")
        
        if not events:
            print("  ❌ No events found!")
            return
        
        latest_event_id = events[0][0]
        print(f"\n📌 Latest event_id: {latest_event_id}")
        
        # 2. Check alarm_audit_trail for this specific event_id
        print(f"\n2️⃣  Checking audit_trail for event_id={latest_event_id}...")
        print("-" * 80)
        cur.execute("""
            SELECT audit_id, event_id, action_type, action_timestamp, performed_by
            FROM historian_raw.alarm_audit_trail
            WHERE event_id = %s
            ORDER BY action_timestamp DESC
        """, (latest_event_id,))
        audit_for_event = cur.fetchall()
        
        print(f"Audit records for THIS event_id ({latest_event_id}): {len(audit_for_event)}")
        for a in audit_for_event:
            audit_id, evt_id, action, ts, user = a
            print(f"  Audit {audit_id} | {action:15s} | {ts} | {user}")
        
        # 3. Check ALL audit_trail records for VYAN1101G (tag_id)
        print(f"\n3️⃣  Checking ALL audit_trail for tag_id='VYAN1101G'...")
        print("-" * 80)
        cur.execute("""
            SELECT audit_id, event_id, action_type, action_timestamp, performed_by
            FROM historian_raw.alarm_audit_trail
            WHERE tag_id = 'VYAN1101G'
            ORDER BY action_timestamp DESC
            LIMIT 20
        """)
        audit_for_tag = cur.fetchall()
        
        print(f"Total audit records for VYAN1101G (all events): {len(audit_for_tag)}")
        
        # Count by action type
        cur.execute("""
            SELECT action_type, COUNT(*) 
            FROM historian_raw.alarm_audit_trail
            WHERE tag_id = 'VYAN1101G'
            GROUP BY action_type
            ORDER BY COUNT(*) DESC
        """)
        action_counts = cur.fetchall()
        
        print("\nAction type breakdown:")
        for action, count in action_counts:
            print(f"  {action:15s}: {count}")
        
        # Count unique event_ids
        cur.execute("""
            SELECT COUNT(DISTINCT event_id) 
            FROM historian_raw.alarm_audit_trail
            WHERE tag_id = 'VYAN1101G'
        """)
        unique_events = cur.fetchone()[0]
        print(f"\nUnique event_ids: {unique_events}")
        
        # 4. Check what event_id=881456 returns
        print(f"\n4️⃣  Checking audit_trail for event_id=881456 (from user screenshot)...")
        print("-" * 80)
        cur.execute("""
            SELECT audit_id, event_id, action_type, action_timestamp, performed_by
            FROM historian_raw.alarm_audit_trail
            WHERE event_id = 881456
            ORDER BY action_timestamp DESC
        """)
        audit_881456 = cur.fetchall()
        
        print(f"Audit records for event_id=881456: {len(audit_881456)}")
        for a in audit_881456[:10]:  # Show first 10
            audit_id, evt_id, action, ts, user = a
            print(f"  Audit {audit_id} | {action:15s} | {ts} | {user}")
        
        if len(audit_881456) > 10:
            print(f"  ... and {len(audit_881456) - 10} more records")
        
        # 5. Check view behavior
        print(f"\n5️⃣  Checking v_alarm_audit_trail view for event_id=881456...")
        print("-" * 80)
        cur.execute("""
            SELECT audit_id, event_id, action_type, action_timestamp, performed_by
            FROM historian_raw.v_alarm_audit_trail
            WHERE event_id = 881456
            ORDER BY action_timestamp DESC
        """)
        view_881456 = cur.fetchall()
        
        print(f"View returns {len(view_881456)} records (should match table)")
        
        # DIAGNOSIS
        print("\n" + "=" * 80)
        print("🔍 DIAGNOSIS:")
        print("=" * 80)
        
        if len(audit_881456) > 5:
            print(f"⚠️  event_id=881456 has {len(audit_881456)} audit records")
            print("   This suggests:")
            print("   A) Multiple alarm occurrences are using SAME event_id (BUG)")
            print("   B) OR alarm was ACKed/CLEARed multiple times (normal)")
            print("   C) OR event_id is being reused across re-triggers (DESIGN ISSUE)")
        
        if unique_events < len(action_counts):
            print(f"\n✅ Multiple event_ids exist ({unique_events})")
            print("   Each alarm occurrence SHOULD have unique event_id")
        
        if len(audit_for_event) != len(audit_881456):
            print(f"\n📌 Latest event {latest_event_id} ≠ 881456")
            print(f"   Latest has {len(audit_for_event)} records")
            print(f"   Event 881456 has {len(audit_881456)} records")
        
        cur.close()
        conn.close()
        
        return True
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    diagnose_audit_data()
