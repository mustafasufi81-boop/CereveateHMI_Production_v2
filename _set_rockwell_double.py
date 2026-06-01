import psycopg2

c = psycopg2.connect(host='localhost', database='Automation_DB',
                     user='cereveate', password='cereveate@222')
cur = c.cursor()

try:
    # ── BEFORE snapshot ──────────────────────────────────────────────
    cur.execute("""
        SELECT tag_id, data_type FROM historian_meta.tag_master
        WHERE server_progid ILIKE 'Rockwel%%' AND enabled = true
          AND lower(data_type) <> 'double'
    """)
    before = cur.fetchall()
    print("BEFORE (non-double Rockwell tags):")
    for r in before:
        print(f"   {r[0]} = {r[1]!r}")

    # ── UPDATE: make ALL Rockwell tags 'double' ──────────────────────
    cur.execute("""
        UPDATE historian_meta.tag_master
        SET data_type = 'double'
        WHERE server_progid ILIKE 'Rockwel%%' AND enabled = true
          AND lower(data_type) <> 'double'
    """)
    print(f"\nRows updated: {cur.rowcount}")

    # ── AFTER verification (still inside txn) ────────────────────────
    cur.execute("""
        SELECT data_type, COUNT(*) FROM historian_meta.tag_master
        WHERE server_progid ILIKE 'Rockwel%%' AND enabled = true
        GROUP BY data_type ORDER BY 2 DESC
    """)
    after = cur.fetchall()
    print("\nAFTER (Rockwell distribution):")
    for r in after:
        print(f"   {r[0]!r:10} -> {r[1]}")

    # Safety: only commit if everything is now 'double'
    if len(after) == 1 and after[0][0] == 'double':
        c.commit()
        print("\n✅ COMMITTED — all Rockwell tags are now 'double'.")
    else:
        c.rollback()
        print("\n⛔ ROLLED BACK — distribution not uniform, no changes saved.")

except Exception as e:
    c.rollback()
    print(f"\n⛔ ERROR, rolled back: {e}")
finally:
    c.close()
