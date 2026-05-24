import psycopg2, psycopg2.extras
conn = psycopg2.connect(host='localhost', port=5432, dbname='Automation_DB', user='cereveate', password='cereveate@222')
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

cur.execute("SELECT pg_get_viewdef('historian_raw.v_daily_hourly_agg', true)")
print("=== v_daily_hourly_agg view definition ===")
r = cur.fetchone()
print(r['pg_get_viewdef'])

cur.execute("SELECT COUNT(*) AS total, SUM(CASE WHEN opc_timestamp IS NULL THEN 1 ELSE 0 END) AS null_opc FROM historian_raw.historian_timeseries")
r = cur.fetchone()
pct = round(r['null_opc'] / r['total'] * 100, 1) if r['total'] else 0
print(f"\n=== NULL opc_timestamp: {r['null_opc']} of {r['total']} rows ({pct}%) ===")

# Check how many rows are covered by v_daily_hourly_agg vs total with value_num
cur.execute("SELECT COUNT(DISTINCT tag_id) AS tags_in_view FROM historian_raw.v_daily_hourly_agg")
print(f"\nTags covered in view: {cur.fetchone()['tags_in_view']}")
cur.execute("SELECT COUNT(DISTINCT tag_id) AS tags_total FROM historian_raw.historian_timeseries WHERE value_num IS NOT NULL AND quality='G'")
print(f"Tags with quality=G data total: {cur.fetchone()['tags_total']}")

conn.close()
