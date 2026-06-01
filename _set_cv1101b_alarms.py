"""Set High alarm limit on CV1101B_AUTO at 28 and Low at 10."""
import psycopg2

c = psycopg2.connect(host='localhost', port=5432, database='Automation_DB',
                     user='cereveate', password='cereveate@222')
cur = c.cursor()

# 1. Show current alarm-related columns
cur.execute("""
    SELECT column_name FROM information_schema.columns
    WHERE table_schema='historian_meta' AND table_name='tag_master'
      AND (column_name ILIKE '%alarm%' OR column_name ILIKE '%limit%' OR column_name ILIKE '%setpoint%')
    ORDER BY ordinal_position
""")
cols = [r[0] for r in cur.fetchall()]
print("Alarm-related columns in tag_master:")
for c1 in cols:
    print(f"  {c1}")

# 2. Show current row
cur.execute(f"SELECT {', '.join(cols)} FROM historian_meta.tag_master WHERE tag_id='CV1101B_AUTO'")
row = cur.fetchone()
print("\nCurrent values for CV1101B_AUTO:")
for col, val in zip(cols, row):
    print(f"  {col} = {val}")

# 3. Update — set High at 28, Low at 10, enable alarms
cur.execute("""
    UPDATE historian_meta.tag_master
    SET alarm_enabled  = TRUE,
        alarm_h_limit  = 28,
        alarm_l_limit  = 10,
        alarm_hh_limit = NULL,
        alarm_ll_limit = NULL
    WHERE tag_id='CV1101B_AUTO'
""")
print(f"\nRows updated: {cur.rowcount}")
c.commit()

# 4. Verify
cur.execute(f"SELECT {', '.join(cols)} FROM historian_meta.tag_master WHERE tag_id='CV1101B_AUTO'")
row = cur.fetchone()
print("\nAfter update:")
for col, val in zip(cols, row):
    print(f"  {col} = {val}")

c.close()
print("\nDone. Restart C# backend to reload alarm config, then watch alarm panel.")
