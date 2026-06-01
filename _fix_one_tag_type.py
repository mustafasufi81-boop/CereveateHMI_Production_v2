import psycopg2

# ════════════════════════════════════════════════════════════════════════════
# UPDATE ONE TAG TO 'REAL' (or any other data_type value)
# 
# INSTRUCTIONS:
# 1. Set TAG_ID or TAG_NAME below (whichever you have)
# 2. Set NEW_TYPE to the value you want ('REAL', 'double', 'integer', etc.)
# 3. Run this script — it will show BEFORE/AFTER and ask for confirmation
# ════════════════════════════════════════════════════════════════════════════

TAG_ID = "TY1102F"           # ← SET THIS (e.g., "TY1102F")
TAG_NAME = None              # ← OR SET THIS (e.g., "Motor_Temp_1")
NEW_TYPE = "REAL"            # ← SET THE NEW data_type VALUE

# ────────────────────────────────────────────────────────────────────────────

c = psycopg2.connect(host='localhost', database='Automation_DB',
                     user='cereveate', password='cereveate@222')
cur = c.cursor()

try:
    # Build WHERE clause
    if TAG_ID:
        where_clause = "tag_id = %s"
        where_value = TAG_ID
    elif TAG_NAME:
        where_clause = "tag_name = %s"
        where_value = TAG_NAME
    else:
        print("ERROR: Set either TAG_ID or TAG_NAME")
        exit(1)

    # ── BEFORE ───────────────────────────────────────────────────────────
    query = f"SELECT tag_id, tag_name, data_type, server_progid FROM historian_meta.tag_master WHERE {where_clause}"
    cur.execute(query, (where_value,))
    row = cur.fetchone()
    
    if not row:
        print(f"ERROR: No tag found matching {where_clause} = {where_value!r}")
        exit(1)

    print("BEFORE:")
    print(f"  tag_id:        {row[0]}")
    print(f"  tag_name:      {row[1]}")
    print(f"  data_type:     {row[2]!r}  ← CURRENT")
    print(f"  server_progid: {row[3]}")
    print(f"\nWILL CHANGE TO: {NEW_TYPE!r}")
    
    # ── UPDATE ───────────────────────────────────────────────────────────
    update = f"UPDATE historian_meta.tag_master SET data_type = %s WHERE {where_clause}"
    cur.execute(update, (NEW_TYPE, where_value))
    
    print(f"\nRows updated: {cur.rowcount}")

    # ── VERIFY ───────────────────────────────────────────────────────────
    cur.execute(query, (where_value,))
    row_after = cur.fetchone()
    
    print("\nAFTER (inside transaction, not yet committed):")
    print(f"  data_type:     {row_after[2]!r}")

    # ── COMMIT OR ROLLBACK ───────────────────────────────────────────────
    if row_after[2] == NEW_TYPE:
        confirm = input("\nCommit this change? (yes/no): ").strip().lower()
        if confirm == 'yes':
            c.commit()
            print("✅ COMMITTED")
        else:
            c.rollback()
            print("⛔ ROLLED BACK (no changes saved)")
    else:
        c.rollback()
        print("⛔ VERIFICATION FAILED — rolled back")

except Exception as e:
    c.rollback()
    print(f"⛔ ERROR: {e}")
finally:
    c.close()
