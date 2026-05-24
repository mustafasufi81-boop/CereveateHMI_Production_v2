import psycopg2, psycopg2.extras
conn = psycopg2.connect("host=localhost dbname=Automation_DB user=cereveate password=cereveate@222")
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

cur.execute("SELECT server_progid, COUNT(tag_id) as cnt FROM historian_meta.tag_master WHERE enabled=true AND server_progid IS NOT NULL GROUP BY server_progid ORDER BY server_progid")
progids = [(r["server_progid"], r["cnt"]) for r in cur.fetchall()]
print("server_progids with enabled tags:")
for p, cnt in progids:
    print(f"  {p}  ({cnt} tags)")

print()
for progid, cnt in progids:
    opc_topic = f"opc/{progid}/tags/bulk"
    cur.execute("SELECT topic_id FROM historian_raw.mqtt_topic_config WHERE topic_name=%s", (opc_topic,))
    existing = cur.fetchone()
    if existing:
        cur.execute("UPDATE historian_raw.mqtt_topic_config SET plc_name=%s, is_active=true WHERE topic_name=%s", (progid, opc_topic))
        print(f"UPDATED  : {opc_topic} -> {progid}")
    else:
        cur.execute("INSERT INTO historian_raw.mqtt_topic_config (topic_name, plc_name, qos, is_active, thread_group) VALUES (%s, %s, 1, true, 1)", (opc_topic, progid))
        print(f"INSERTED : {opc_topic} -> {progid}")

conn.commit()
print()
cur.execute("SELECT topic_name, plc_name FROM historian_raw.mqtt_topic_config WHERE is_active=true ORDER BY topic_name")
print("Active topics:")
for r in cur.fetchall():
    print(f"  {r['topic_name']}  ->  {r['plc_name']}")
conn.close()
