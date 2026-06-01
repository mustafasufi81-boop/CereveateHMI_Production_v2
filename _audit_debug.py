import psycopg2
conn = psycopg2.connect(host='localhost', dbname='Automation_DB', user='cereveate', password='cereveate@222')
cur = conn.cursor()

# Check if event_ids exist in historian_events
test_ids = [97934, 97937, 85105, 97941, 881184]
for eid in test_ids:
    cur.execute('SELECT event_id, tag_id, event_type, time FROM historian_raw.historian_events WHERE event_id = %s', (eid,))
    row = cur.fetchone()
    print('historian_events event_id=%s: %s' % (eid, row))

# Check if v_alarm_audit_trail view exists
cur.execute("SELECT COUNT(*) FROM information_schema.views WHERE table_schema='historian_raw' AND table_name='v_alarm_audit_trail'")
print('v_alarm_audit_trail view exists:', cur.fetchone()[0] > 0)

# Check alarm_audit_trail columns
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='historian_raw' AND table_name='alarm_audit_trail' ORDER BY ordinal_position")
print('audit_trail columns:', [r[0] for r in cur.fetchall()])

# Check where RAISED records come from - does the mqtt_subscriber write them?
cur.execute("SELECT action_type, COUNT(*) FROM historian_raw.alarm_audit_trail GROUP BY action_type ORDER BY count DESC")
print('Audit action type counts:')
for r in cur.fetchall():
    print('  %s: %d' % (r[0], r[1]))

# Show a sample event_id that DOES have audit records to understand the flow
cur.execute("SELECT DISTINCT event_id FROM historian_raw.alarm_audit_trail LIMIT 5")
good_ids = [r[0] for r in cur.fetchall()]
print('Event_ids that DO have audit records:', good_ids)

# Check if those good event_ids are in alarm_active too
for eid in good_ids[:3]:
    cur.execute('SELECT current_event_id, tag_id FROM historian_raw.alarm_active WHERE current_event_id = %s', (eid,))
    row = cur.fetchone()
    print('  event_id=%s in alarm_active: %s' % (eid, row))

conn.close()
