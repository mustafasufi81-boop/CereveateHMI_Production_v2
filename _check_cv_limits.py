import psycopg2
c = psycopg2.connect(host='localhost', port=5432, database='Automation_DB',
                     user='cereveate', password='cereveate@222')
cur = c.cursor()
cur.execute("""
    SELECT alarm_enabled, alarm_h_limit, alarm_l_limit, alarm_hh_limit, alarm_ll_limit,
           alarm_high_threshold, alarm_low_threshold,
           alarm_high_high_threshold, alarm_low_low_threshold
    FROM historian_meta.tag_master WHERE tag_id='CV1101B_AUTO'
""")
print(cur.fetchone())
c.close()
