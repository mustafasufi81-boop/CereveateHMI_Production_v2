import psycopg2
conn = psycopg2.connect(host='localhost',port=5432,database='Automation_DB',user='cereveate',password='cereveate@222')
cur = conn.cursor()
tables = [
    'historian_meta.plants_areas',
    'historian_meta.user_area_assignments',
    'historian_meta.access_audit_log',
    'historian_meta.roles',
    'historian_meta.users',
    'historian_meta.role_tag_permissions',
]
for t in tables:
    schema, name = t.split('.')
    cur.execute("""
        SELECT column_name, data_type, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_schema=%s AND table_name=%s
        ORDER BY ordinal_position
    """, (schema, name))
    rows = cur.fetchall()
    print(f'\n=== {t} ===')
    for r in rows:
        print(f'  {r[0]:35s} {r[1]:20s} nullable={r[2]}')
conn.close()
