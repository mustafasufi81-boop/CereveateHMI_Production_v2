import psycopg2

conn = psycopg2.connect(host='localhost', port=5432, dbname='Automation_DB', user='cereveate', password='cereveate@222')
cur = conn.cursor()

cur.execute("SHOW config_file;")
print("config_file:", cur.fetchone()[0])

cur.execute("SHOW shared_preload_libraries;")
print("shared_preload_libraries:", cur.fetchone()[0])

cur.execute("SHOW shared_buffers;")
print("shared_buffers:", cur.fetchone()[0])

cur.execute("SHOW work_mem;")
print("work_mem:", cur.fetchone()[0])

cur.execute("SHOW max_wal_size;")
print("max_wal_size:", cur.fetchone()[0])

cur.close()
conn.close()
