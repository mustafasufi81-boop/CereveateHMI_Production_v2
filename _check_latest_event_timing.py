"""
CRITICAL CHECK: When was the LAST PLC alarm event generated?
- If latest PLC event is ~22:47 (freeze time) → NO BUG (events stopped at disconnect)
- If latest PLC event is recent (03:00+) → BUG (still evaluating frozen values)
"""
import psycopg2
from datetime import datetime

conn = psycopg2.connect(
    host="localhost",
    database="Automation_DB",
    user="cereveate",
    password="cereveate@222"
)
cur = conn.cursor()

print("=" * 70)
print("LATEST ALARM EVENT TIMING - PLC vs OPC")
print(f"Current time: {datetime.now().strftime('%H:%M:%S')}")
print("PLC froze at: 22:47:29 (last good read)")
print("=" * 70)

# Latest PLC tag alarm event
print("\n[1] LATEST PLC TAG ALARM EVENTS (Rockwel_PLC_001 tags):")
cur.execute("""
    SELECT 
        he.tag_id,
        he.time,
        he.alarm_state,
        he.alarm_level,
        he.alarm_actual_value
    FROM historian_raw.historian_events he
    INNER JOIN historian_meta.tag_master tm ON he.tag_id = tm.tag_id
    WHERE tm.plc_ip_address = '192.168.0.20'
    ORDER BY he.time DESC
    LIMIT 10
""")

rows = cur.fetchall()
for tag, ts, state, level, value in rows:
    print(f"   {ts} | {tag:<12} {level}:{state} = {value}")

if rows:
    latest_plc = rows[0][1]
    print(f"\n   >>> LATEST PLC EVENT: {latest_plc}")

# Latest OPC tag alarm event (for comparison)
print("\n[2] LATEST OPC TAG ALARM EVENTS (Matrikon simulation):")
cur.execute("""
    SELECT 
        he.tag_id,
        he.time,
        he.alarm_state,
        he.alarm_level
    FROM historian_raw.historian_events he
    INNER JOIN historian_meta.tag_master tm ON he.tag_id = tm.tag_id
    WHERE tm.server_progid LIKE '%Matrikon%'
    ORDER BY he.time DESC
    LIMIT 5
""")

opc_rows = cur.fetchall()
for tag, ts, state, level in opc_rows:
    print(f"   {ts} | {tag:<20} {level}:{state}")

if opc_rows:
    latest_opc = opc_rows[0][1]
    print(f"\n   >>> LATEST OPC EVENT: {latest_opc}")

# Count PLC events in last 30 minutes (these would be the BUG)
print("\n[3] PLC ALARM EVENTS IN LAST 30 MINUTES (these = BUG if any):")
cur.execute("""
    SELECT COUNT(*)
    FROM historian_raw.historian_events he
    INNER JOIN historian_meta.tag_master tm ON he.tag_id = tm.tag_id
    WHERE tm.plc_ip_address = '192.168.0.20'
    AND he.time > NOW() - INTERVAL '30 minutes'
""")
plc_recent = cur.fetchone()[0]

cur.execute("""
    SELECT COUNT(*)
    FROM historian_raw.historian_events he
    INNER JOIN historian_meta.tag_master tm ON he.tag_id = tm.tag_id
    WHERE tm.server_progid LIKE '%Matrikon%'
    AND he.time > NOW() - INTERVAL '30 minutes'
""")
opc_recent = cur.fetchone()[0]

print(f"   PLC events (last 30 min): {plc_recent}")
print(f"   OPC events (last 30 min): {opc_recent}")

conn.close()

print("\n" + "=" * 70)
print("VERDICT:")
print("=" * 70)
if plc_recent > 0:
    print(f"❌ BUG: {plc_recent} PLC alarm events in last 30 min (PLC is disconnected!)")
    print("   AlarmEvaluationService is evaluating frozen Uncertain-quality values")
    print("   FIX NEEDED: Restart C# service with quality-check (already built)")
else:
    print(f"✅ NO BUG: 0 PLC events in last 30 min (correctly stopped at disconnect)")
    print(f"   The {opc_recent} OPC events are legitimate (simulation still running)")
    print("   Your screenshot history shows OLD events from before disconnect")
