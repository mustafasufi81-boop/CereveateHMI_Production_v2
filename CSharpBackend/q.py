import psycopg2
conn = psycopg2.connect(host='localhost',port=5432,dbname='Automation_DB',user='cereveate',password='cereveate@222')
cur = conn.cursor()
cur.execute("""SELECT tag_id, enabled FROM historian_meta.tag_master WHERE server_progid='Rockwel_PLC_001' AND enabled=true ORDER BY tag_id""")
print('Enabled tags:', cur.fetchall())
# Also check DB loader fallback - is another PLC causing the exception?
cur.execute("""
    SELECT DISTINCT server_progid, plc_ip_address, plc_port
    FROM historian_meta.tag_master
    WHERE server_progid IS NOT NULL AND enabled=true AND plc_ip_address IS NOT NULL
    ORDER BY server_progid
""")
print('PLCs from DB loader query:', cur.fetchall())
conn.close()
