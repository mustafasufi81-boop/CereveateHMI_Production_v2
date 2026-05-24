import psycopg2, psycopg2.extras

conn = psycopg2.connect(host='localhost', port=5432, dbname='Automation_DB', user='cereveate', password='cereveate@222')
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

# 1. Full live trigger function source
print('=== LIVE TRIGGER FUNCTION ===')
cur.execute("""
    SELECT pg_get_functiondef(p.oid) AS src
    FROM pg_proc p
    WHERE p.proname = 'fn_auto_add_tag_to_report_template'
      AND p.pronamespace = (SELECT n.oid FROM pg_namespace n WHERE n.nspname = 'historian_meta')
""")
row = cur.fetchone()
print(row['src'] if row else 'NOT FOUND')

# 2. Pick a Matrikon tag that has report_flag=TRUE
print('\n=== MATRIKON TAGS WITH report_flag=TRUE (first 5) ===')
cur.execute("""
    SELECT tag_id, tag_name, server_progid, report_flag, include_in_report
    FROM historian_meta.tag_master
    WHERE server_progid ILIKE '%matrikon%'
      AND (report_flag = TRUE OR include_in_report = TRUE)
    ORDER BY tag_id
    LIMIT 5
""")
for r in cur.fetchall(): print(dict(r))

# 3. Check what report_templates has for the first Matrikon tag
print('\n=== report_templates for first Matrikon tag ===')
cur.execute("""
    SELECT rt.report_type, rt.s_no, rt.tag_id, rt.enabled
    FROM historian_meta.report_templates rt
    JOIN historian_meta.tag_master tm ON tm.tag_id = rt.tag_id
    WHERE tm.server_progid ILIKE '%matrikon%'
      AND (tm.report_flag = TRUE OR tm.include_in_report = TRUE)
    ORDER BY rt.tag_id, rt.report_type
    LIMIT 15
""")
for r in cur.fetchall(): print(dict(r))

# 4. Check what column the trigger actually uses: report_flag vs include_in_report
print('\n=== tag_master columns (check report_flag vs include_in_report) ===')
cur.execute("""
    SELECT column_name, data_type
    FROM information_schema.columns
    WHERE table_schema = 'historian_meta' AND table_name = 'tag_master'
      AND column_name IN ('report_flag','include_in_report')
""")
for r in cur.fetchall(): print(dict(r))

cur.close()
conn.close()
