import psycopg2

c = psycopg2.connect(host='localhost', database='Automation_DB',
                     user='cereveate', password='cereveate@222')
cur = c.cursor()

cur.execute("""
    SELECT conname, pg_get_constraintdef(oid)
    FROM pg_constraint
    WHERE conrelid = 'historian_meta.tag_master'::regclass
      AND contype = 'c'
    ORDER BY conname
""")
print("=== CHECK constraints on historian_meta.tag_master ===")
for r in cur.fetchall():
    print(f"\n{r[0]}:\n  {r[1]}")

c.close()
