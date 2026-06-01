import psycopg2

c = psycopg2.connect(host='localhost', database='Automation_DB',
                     user='cereveate', password='cereveate@222')
cur = c.cursor()

try:
    # Check current state
    cur.execute("""
        SELECT tag_id, tag_name, data_type, server_progid 
        FROM historian_meta.tag_master 
        WHERE tag_name = 'TY1102F'
    """)
    before = cur.fetchone()
    print(f"BEFORE: {before}")
    
    # Update to double
    cur.execute("""
        UPDATE historian_meta.tag_master 
        SET data_type = 'double'
        WHERE tag_name = 'TY1102F' 
          AND server_progid ILIKE 'Rockwel%'
    """)
    print(f"Rows updated: {cur.rowcount}")
    
    # Verify
    cur.execute("""
        SELECT tag_id, tag_name, data_type, server_progid 
        FROM historian_meta.tag_master 
        WHERE tag_name = 'TY1102F'
    """)
    after = cur.fetchone()
    print(f"AFTER:  {after}")
    
    # Commit if successful
    c.commit()
    print("\n✅ COMMITTED — TY1102F is now 'double'")
    
except Exception as e:
    c.rollback()
    print(f"\n⛔ ERROR (rolled back): {e}")
finally:
    c.close()
