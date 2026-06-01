"""
Read CV1101B from tag_master, insert CV1101B_AUTO with slot=2, then restart hint.
"""
import psycopg2, json, sys

DB = dict(dbname='Automation_DB', user='cereveate', password='cereveate@222', host='127.0.0.1', port=5432)

def main():
    conn = psycopg2.connect(**DB)
    conn.autocommit = False
    cur = conn.cursor()

    # --- 1. Get columns ---
    cur.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'historian_meta' AND table_name = 'tag_master'
        ORDER BY ordinal_position
    """)
    cols = [r[0] for r in cur.fetchall()]
    print(f"Columns ({len(cols)}): {cols}\n")

    # --- 2. Read source row ---
    cur.execute("SELECT * FROM historian_meta.tag_master WHERE tag_id ILIKE %s LIMIT 1", ('%CV1101B%',))
    row = cur.fetchone()
    if not row:
        print("ERROR: No row matching CV1101B found!")
        conn.close()
        sys.exit(1)

    src = dict(zip(cols, row))
    print("SOURCE ROW (CV1101B):")
    print(json.dumps(src, default=str, indent=2))

    # --- 3. Check if target already exists ---
    cur.execute("SELECT tag_id FROM historian_meta.tag_master WHERE tag_id = %s", ('CV1101B_AUTO',))
    if cur.fetchone():
        print("\nCV1101B_AUTO already exists — updating slot to 2...")
        cur.execute("""
            UPDATE historian_meta.tag_master
            SET slot = 2
            WHERE tag_id = 'CV1101B_AUTO'
        """)
        conn.commit()
        print("Updated.")
        conn.close()
        return

    # --- 4. Build new row: copy source, change tag_id, server_prog_id, slot ---
    new = dict(src)
    new['tag_id']         = 'CV1101B_AUTO'
    new['server_prog_id'] = 'CV1101B_AUTO'   # user instruction: change server_prog_id
    new['slot']           = 2                # user instruction: slot = 2

    # Columns and values for INSERT (skip any serial/generated cols if present)
    insert_cols = [c for c in cols]
    placeholders = ', '.join(['%s'] * len(insert_cols))
    col_list     = ', '.join(insert_cols)
    values       = [new[c] for c in insert_cols]

    sql = f"INSERT INTO historian_meta.tag_master ({col_list}) VALUES ({placeholders})"
    print(f"\nInserting CV1101B_AUTO ...")
    try:
        cur.execute(sql, values)
        conn.commit()
        print("INSERT OK")
    except Exception as e:
        conn.rollback()
        print(f"INSERT FAILED: {e}")
        # Try without potentially auto-generated cols
        skip = {'id', 'created_at', 'updated_at'}
        insert_cols2 = [c for c in cols if c not in skip]
        placeholders2 = ', '.join(['%s'] * len(insert_cols2))
        col_list2     = ', '.join(insert_cols2)
        values2       = [new[c] for c in insert_cols2]
        sql2 = f"INSERT INTO historian_meta.tag_master ({col_list2}) VALUES ({placeholders2})"
        print(f"Retrying without auto cols {skip} ...")
        cur.execute(sql2, values2)
        conn.commit()
        print("INSERT OK (2nd attempt)")

    # --- 5. Verify ---
    cur.execute("SELECT * FROM historian_meta.tag_master WHERE tag_id = 'CV1101B_AUTO'")
    inserted = dict(zip(cols, cur.fetchone()))
    print("\nINSERTED ROW:")
    print(json.dumps(inserted, default=str, indent=2))

    conn.close()
    print("\n✅ Done. Restart OpcDaWebBrowser to pick up the new tag.")

if __name__ == '__main__':
    main()
