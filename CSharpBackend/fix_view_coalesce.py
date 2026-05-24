"""Fix v_daily_hourly_agg to use COALESCE(opc_timestamp, time) so rows where opc_timestamp IS NULL still appear in reports."""
import psycopg2

conn = psycopg2.connect(host='localhost', port=5432, dbname='Automation_DB', user='cereveate', password='cereveate@222')
conn.autocommit = True
cur = conn.cursor()

sql = """
CREATE OR REPLACE VIEW historian_raw.v_daily_hourly_agg AS
SELECT
    tag_id,
    date((COALESCE(opc_timestamp, "time") AT TIME ZONE 'Asia/Kolkata')) AS local_date,
    EXTRACT(hour FROM (COALESCE(opc_timestamp, "time") AT TIME ZONE 'Asia/Kolkata'))::integer AS local_hour,
    round(avg(value_num)::numeric, 2) AS avg_val,
    round(max(value_num)::numeric, 2) AS max_val,
    round(min(value_num)::numeric, 2) AS min_val
FROM historian_raw.historian_timeseries ht
WHERE quality = 'G'
  AND value_num IS NOT NULL
GROUP BY
    tag_id,
    date((COALESCE(opc_timestamp, "time") AT TIME ZONE 'Asia/Kolkata')),
    EXTRACT(hour FROM (COALESCE(opc_timestamp, "time") AT TIME ZONE 'Asia/Kolkata'));
"""

cur.execute(sql)
print("View recreated successfully with COALESCE(opc_timestamp, time)")

# Verify row count improvement
cur.execute("SELECT COUNT(*) FROM historian_raw.v_daily_hourly_agg")
print(f"Total agg rows now: {cur.fetchone()[0]}")
cur.execute("SELECT COUNT(DISTINCT tag_id) FROM historian_raw.v_daily_hourly_agg")
print(f"Tags covered in view: {cur.fetchone()[0]}")

conn.close()
