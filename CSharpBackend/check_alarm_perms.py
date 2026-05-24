import psycopg2
conn = psycopg2.connect(dbname='Automation_DB', user='cereveate', password='cereveate@222', host='localhost')
cur = conn.cursor()

cur.execute("""
    ALTER TABLE historian_meta.users
    ADD COLUMN IF NOT EXISTS must_change_password BOOLEAN NOT NULL DEFAULT FALSE
""")
conn.commit()
print("Column must_change_password added (or already exists).")

cur.execute("SELECT column_name, data_type, column_default FROM information_schema.columns WHERE table_schema='historian_meta' AND table_name='users' AND column_name='must_change_password'")
print(cur.fetchone())
conn.close()
