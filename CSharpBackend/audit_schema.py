import psycopg2
conn = psycopg2.connect(dbname='Automation_DB', user='cereveate', password='cereveate@222', host='localhost', port=5432)
cur = conn.cursor()

cur.execute("SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema IN ('historian_raw','historian_meta') AND table_name LIKE '%alarm%' ORDER BY 1,2")
print('ALARM TABLES:', cur.fetchall())

cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='historian_raw' AND table_name='historian_events' ORDER BY ordinal_position")
print('historian_events:', [r[0] for r in cur.fetchall()])

cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='historian_raw' AND table_name='alarm_active' ORDER BY ordinal_position")
print('alarm_active:', [r[0] for r in cur.fetchall()])

cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='historian_meta' AND table_name='tag_master' ORDER BY ordinal_position")
print('tag_master:', [r[0] for r in cur.fetchall()])

cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='historian_raw' AND table_name='alarm_audit_trail' ORDER BY ordinal_position")
print('alarm_audit_trail:', [r[0] for r in cur.fetchall()])

cur.execute("SELECT COUNT(*) FROM historian_raw.historian_events")
print('historian_events count:', cur.fetchone()[0])

cur.execute("SELECT alarm_state, COUNT(*) FROM historian_raw.historian_events GROUP BY alarm_state")
print('states:', cur.fetchall())

cur.execute("SELECT COUNT(*) FROM historian_raw.alarm_active")
print('alarm_active count:', cur.fetchone()[0])

# Check if operator_notes, shelve columns exist
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='historian_raw' AND table_name IN ('historian_events','alarm_active') AND column_name IN ('operator_notes','shelved_at','shelved_by','shelve_expires_at','is_event','quality','quality_state','flood_suppressed')")
print('enhancement cols already present:', [r[0] for r in cur.fetchall()])

conn.close()
print('DONE')
