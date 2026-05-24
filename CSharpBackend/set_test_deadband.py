import psycopg2
conn = psycopg2.connect(host='localhost', dbname='Automation_DB', user='cereveate', password='cereveate@222')
cur = conn.cursor()
cur.execute("UPDATE historian_meta.tag_master SET alarm_deadband=1 WHERE tag_id IN ('Random.Real4', 'Triangle Waves.Real4')")
conn.commit()
cur.execute("SELECT tag_id, alarm_deadband, alarm_h_limit, alarm_l_limit, alarm_hh_limit, alarm_ll_limit FROM historian_meta.tag_master WHERE tag_id IN ('Random.Real4', 'Triangle Waves.Real4')")
for r in cur.fetchall():
    print(r)
conn.close()
print('Deadband set to 1 for both tags')
