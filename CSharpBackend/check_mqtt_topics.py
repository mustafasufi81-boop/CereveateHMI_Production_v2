import psycopg2
c = psycopg2.connect('host=localhost dbname=Automation_DB user=cereveate password=cereveate@222')
cur = c.cursor()
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='historian_raw' AND table_name='mqtt_topic_config' ORDER BY ordinal_position")
print("COLUMNS:", [r[0] for r in cur.fetchall()])
cur.execute("SELECT * FROM historian_raw.mqtt_topic_config")
print("ROWS:")
for r in cur.fetchall():
    print(" ", r)
c.close()
