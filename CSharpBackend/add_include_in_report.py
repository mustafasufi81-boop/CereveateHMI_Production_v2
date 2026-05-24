import psycopg2

conn = psycopg2.connect(host='localhost', port=5432, dbname='Automation_DB', user='cereveate', password='cereveate@222')
conn.autocommit = True
cur = conn.cursor()

cur.execute("""
    ALTER TABLE historian_meta.tag_master
    ADD COLUMN IF NOT EXISTS include_in_report BOOLEAN NOT NULL DEFAULT TRUE
""")

cur.execute("""
    COMMENT ON COLUMN historian_meta.tag_master.include_in_report
    IS 'Flag to include this tag in reports when using automatic tag selection by source/topic'
""")

cur.execute("SELECT COUNT(*) FROM historian_meta.tag_master WHERE include_in_report = TRUE")
count = cur.fetchone()[0]
print(f"Column added OK. Tags with include_in_report=TRUE: {count}")

# Check new column exists
cur.execute("""
    SELECT column_name, data_type, column_default
    FROM information_schema.columns
    WHERE table_schema = 'historian_meta' AND table_name = 'tag_master' AND column_name = 'include_in_report'
""")
row = cur.fetchone()
print(f"Column info: {row}")

conn.close()
