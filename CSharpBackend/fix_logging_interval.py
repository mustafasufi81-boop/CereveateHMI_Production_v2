import psycopg2
conn = psycopg2.connect(host='localhost', port=5432, dbname='Automation_DB', user='cereveate', password='cereveate@222')
cur = conn.cursor()
cur.execute("""
    UPDATE historian_meta.tag_master
    SET logging_interval_ms = 1000,
        db_logging_interval_ms = 1000,
        plc_polling_interval_ms = 1000
    WHERE tag_id = 'TY1101A'
""")
conn.commit()
cur.execute("SELECT tag_id, logging_interval_ms, db_logging_interval_ms, plc_polling_interval_ms FROM historian_meta.tag_master WHERE tag_id = 'TY1101A'")
print(cur.fetchone())
conn.close()
