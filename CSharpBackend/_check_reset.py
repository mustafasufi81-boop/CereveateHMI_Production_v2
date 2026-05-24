import psycopg2

conn = psycopg2.connect(dbname='Automation_DB', user='cereveate', password='cereveate@222', host='localhost')
cur = conn.cursor()

# Check columns
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='historian_meta' AND table_name='users' ORDER BY ordinal_position")
cols = [r[0] for r in cur.fetchall()]
print("COLUMNS:", cols)

# Try reset directly
try:
    cur.execute("""
        UPDATE historian_meta.users
        SET must_change_password = TRUE,
            password_hash        = 'RESET_REQUIRED',
            security_questions   = NULL
        WHERE id = 3
    """)
    print("ROWCOUNT:", cur.rowcount)
    conn.rollback()  # don't actually change
    print("SQL OK - rollback done")
except Exception as e:
    print("SQL ERROR:", e)
    conn.rollback()

conn.close()
