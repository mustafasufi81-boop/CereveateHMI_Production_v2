import psycopg2
from datetime import datetime

c = psycopg2.connect(host='localhost', database='Automation_DB',
                     user='cereveate', password='cereveate@222')
c.autocommit = False
cur = c.cursor()

TARGET = 'REAL'

# 1) BACKUP current values (Rockwell PLC tags only) to a timestamped file
cur.execute("""
    SELECT tag_id, server_progid, tag_name, data_type
    FROM historian_meta.tag_master
    WHERE server_progid ILIKE 'Rockwel%' AND enabled = true
    ORDER BY server_progid, tag_name
""")
rows = cur.fetchall()
stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
backup_file = f'rockwell_datatype_backup_{stamp}.csv'
with open(backup_file, 'w', encoding='utf-8') as f:
    f.write("tag_id,server_progid,tag_name,old_data_type\n")
    for r in rows:
        f.write(f"{r[0]},{r[1]},{r[2]},{r[3]}\n")
print(f"[BACKUP] {len(rows)} Rockwell tags -> {backup_file}")

# Show the BEFORE distribution
cur.execute("""
    SELECT data_type, COUNT(*)
    FROM historian_meta.tag_master
    WHERE server_progid ILIKE 'Rockwel%' AND enabled = true
    GROUP BY data_type ORDER BY 2 DESC
""")
print("\nBEFORE:")
for r in cur.fetchall():
    print(f"  {r[0]!r:10} -> {r[1]}")

# 2) UPDATE — set all Rockwell PLC tags to REAL
# NOTE: '%%' escapes the literal percent because this query carries a %s param.
cur.execute("""
    UPDATE historian_meta.tag_master
    SET data_type = %s
    WHERE server_progid ILIKE 'Rockwel%%' AND enabled = true
""", (TARGET,))
updated = cur.rowcount
print(f"\n[UPDATE] rows affected = {updated}")

# 3) VERIFY within the same transaction (not yet committed)
cur.execute("""
    SELECT data_type, COUNT(*)
    FROM historian_meta.tag_master
    WHERE server_progid ILIKE 'Rockwel%' AND enabled = true
    GROUP BY data_type ORDER BY 2 DESC
""")
print("\nAFTER (pre-commit):")
after = cur.fetchall()
for r in after:
    print(f"  {r[0]!r:10} -> {r[1]}")

# Safety: only commit if everything is now REAL and count matches
ok = (len(after) == 1 and after[0][0] == TARGET and after[0][1] == len(rows))
if ok:
    c.commit()
    print(f"\n[COMMIT] OK — all {len(rows)} Rockwell tags set to {TARGET!r}.")
else:
    c.rollback()
    print("\n[ROLLBACK] Unexpected state — NO changes saved. Investigate.")

c.close()
