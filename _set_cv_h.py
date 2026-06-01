import psycopg2
c = psycopg2.connect(host='localhost', port=5432, database='Automation_DB',
                     user='cereveate', password='cereveate@222')
cur = c.cursor()
cur.execute("""
    UPDATE historian_meta.tag_master
    SET alarm_enabled=TRUE,
        alarm_h_limit=28,
        alarm_l_limit=NULL,
        alarm_hh_limit=NULL,
        alarm_ll_limit=NULL,
        alarm_high_threshold=28,
        alarm_low_threshold=NULL,
        alarm_high_high_threshold=NULL,
        alarm_low_low_threshold=NULL
    WHERE tag_id='CV1101B_AUTO'
""")
print('rows updated:', cur.rowcount)
c.commit()
cur.execute("""
    SELECT alarm_enabled, alarm_h_limit, alarm_high_threshold,
           alarm_l_limit, alarm_low_threshold, alarm_priority
    FROM historian_meta.tag_master WHERE tag_id='CV1101B_AUTO'
""")
print('result:', cur.fetchone())
c.close()
