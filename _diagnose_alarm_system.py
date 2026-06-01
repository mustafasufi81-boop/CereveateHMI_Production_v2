import psycopg2
import time

conn = psycopg2.connect(
    dbname="Automation_DB",
    user="cereveate",
    password="cereveate@222",
    host="localhost",
    port="5432"
)

cur = conn.cursor()

print("=" * 80)
print("DEEP ANALYSIS: WHY ALARMS ARE NOT APPEARING")
print("=" * 80)

# 1. Check if alarm_active is empty
print("\n[1] CHECKING alarm_active TABLE:")
cur.execute("SELECT COUNT(*) FROM historian_raw.alarm_active")
active_count = cur.fetchone()[0]
print(f"   Active alarms in database: {active_count}")

# 2. Check recent historian_events for new RAISED events
print("\n[2] CHECKING historian_events FOR NEW ALARM_RAISED EVENTS:")
cur.execute("""
    SELECT 
        event_id,
        tag_id,
        event_type,
        time,
        alarm_actual_value,
        alarm_setpoint
    FROM historian_raw.historian_events
    WHERE event_type LIKE 'ALARM_RAISED%'
    AND time > NOW() - INTERVAL '10 minutes'
    ORDER BY time DESC
    LIMIT 10
""")
recent_raised = cur.fetchall()
print(f"   ALARM_RAISED events in last 10 minutes: {len(recent_raised)}")
if recent_raised:
    for row in recent_raised:
        event_id, tag_id, event_type, time, value, setpoint = row
        print(f"   - {tag_id} ({event_type}) at {time}: value={value}, setpoint={setpoint}")
else:
    print("   ⚠️ NO ALARM_RAISED events in last 10 minutes!")

# 3. Check current tag values that SHOULD be triggering alarms
print("\n[3] CHECKING CURRENT TAG VALUES VS ALARM LIMITS:")
cur.execute("""
    SELECT 
        tm.tag_id,
        tm.tag_name,
        alc.level,
        alc.setpoint,
        alc.comparison_operator,
        tm.value as current_value,
        tm.updated_at as value_timestamp,
        CASE 
            WHEN alc.comparison_operator = '>' AND tm.value > alc.setpoint THEN 'SHOULD ALARM'
            WHEN alc.comparison_operator = '<' AND tm.value < alc.setpoint THEN 'SHOULD ALARM'
            WHEN alc.comparison_operator = '>=' AND tm.value >= alc.setpoint THEN 'SHOULD ALARM'
            WHEN alc.comparison_operator = '<=' AND tm.value <= alc.setpoint THEN 'SHOULD ALARM'
            ELSE 'NORMAL'
        END as alarm_status
    FROM historian_meta.tag_master tm
    INNER JOIN historian_meta.alarm_limits_config alc ON tm.tag_id = alc.tag_id
    WHERE tm.value IS NOT NULL
    AND alc.enabled = TRUE
    ORDER BY value_timestamp DESC
    LIMIT 20
""")
tag_values = cur.fetchall()
print(f"   Tags with alarm limits configured: {len(tag_values)}")

should_alarm_count = 0
for row in tag_values:
    tag_id, tag_name, level, setpoint, operator, current_value, ts, status = row
    if status == 'SHOULD ALARM':
        should_alarm_count += 1
        print(f"   🔴 {tag_id} ({level}): value={current_value} {operator} {setpoint} - {status}")

if should_alarm_count == 0:
    print("   ✅ No tags currently exceeding alarm limits (all values normal)")

# 4. Check if alarm evaluation service is writing to database
print("\n[4] CHECKING RECENT HISTORIAN_EVENTS (ANY TYPE):")
cur.execute("""
    SELECT 
        event_type,
        COUNT(*) as count,
        MAX(time) as latest_time
    FROM historian_raw.historian_events
    WHERE time > NOW() - INTERVAL '5 minutes'
    GROUP BY event_type
    ORDER BY latest_time DESC
""")
recent_events = cur.fetchall()
if recent_events:
    print(f"   Recent events in last 5 minutes:")
    for event_type, count, latest_time in recent_events:
        print(f"   - {event_type}: {count} events (latest: {latest_time})")
else:
    print("   ⚠️ NO events written to historian_events in last 5 minutes!")
    print("   This suggests C# backend may not be running or not writing to DB")

# 5. Check alarm_limits_config
print("\n[5] CHECKING ALARM LIMITS CONFIGURATION:")
cur.execute("""
    SELECT 
        COUNT(*) as total_limits,
        COUNT(CASE WHEN enabled = TRUE THEN 1 END) as enabled_limits,
        COUNT(CASE WHEN enabled = FALSE THEN 1 END) as disabled_limits
    FROM historian_meta.alarm_limits_config
""")
config_stats = cur.fetchone()
total, enabled, disabled = config_stats
print(f"   Total alarm limits: {total}")
print(f"   Enabled: {enabled}")
print(f"   Disabled: {disabled}")

if enabled == 0:
    print("   ⚠️ NO ENABLED ALARM LIMITS! Alarms cannot trigger.")

# 6. Check tag_master for recent value updates
print("\n[6] CHECKING TAG_MASTER FOR RECENT UPDATES:")
cur.execute("""
    SELECT 
        COUNT(*) as total_tags,
        COUNT(CASE WHEN updated_at > NOW() - INTERVAL '1 minute' THEN 1 END) as updated_last_minute,
        MAX(updated_at) as latest_update
    FROM historian_meta.tag_master
    WHERE value IS NOT NULL
""")
tag_stats = cur.fetchone()
total_tags, recent_updates, latest_update = tag_stats
print(f"   Total tags with values: {total_tags}")
print(f"   Updated in last 1 minute: {recent_updates}")
print(f"   Latest update timestamp: {latest_update}")

if recent_updates == 0:
    print("   ⚠️ NO TAG VALUES UPDATED IN LAST MINUTE!")
    print("   This suggests PLC data is not flowing into tag_master")

cur.close()
conn.close()

print("\n" + "=" * 80)
print("DIAGNOSIS SUMMARY:")
print("=" * 80)
print("\n✅ = OK | ⚠️ = PROBLEM\n")

issues = []
if active_count == 0 and should_alarm_count > 0:
    issues.append("Tags should be alarming but alarm_active is empty")
if len(recent_raised) == 0 and should_alarm_count > 0:
    issues.append("No ALARM_RAISED events being written despite alarm conditions")
if len(recent_events) == 0:
    issues.append("C# backend not writing ANY events to historian_events")
if enabled == 0:
    issues.append("All alarm limits are DISABLED in configuration")
if recent_updates == 0:
    issues.append("Tag values not being updated - PLC data flow issue")

if issues:
    print("PROBLEMS FOUND:")
    for i, issue in enumerate(issues, 1):
        print(f"  {i}. {issue}")
else:
    print("All systems appear normal. Alarms will trigger when values exceed limits.")

print("\n" + "=" * 80)
