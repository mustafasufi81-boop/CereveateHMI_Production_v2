import psycopg2

try:
    conn = psycopg2.connect(
        host='localhost',
        port=5432,
        dbname='Automation_DB',
        user='cereveate',
        password='cereveate@222'
    )
    cur = conn.cursor()
    
    # Update all three shifts
    # Shift A (Morning): 5 AM - 1 PM
    cur.execute("""
        UPDATE historian_meta.shifts 
        SET start_time = '05:00:00',
            end_time = '13:00:00'
        WHERE shift_code = 'SHIFT_A'
    """)
    
    # Shift B (Afternoon): 1 PM - 9 PM
    cur.execute("""
        UPDATE historian_meta.shifts 
        SET start_time = '13:00:00',
            end_time = '21:00:00'
        WHERE shift_code = 'SHIFT_B'
    """)
    
    # Shift C (Night): 9 PM - 5 AM (next day)
    cur.execute("""
        UPDATE historian_meta.shifts 
        SET start_time = '21:00:00',
            end_time = '05:00:00'
        WHERE shift_code = 'SHIFT_C'
    """)
    
    conn.commit()
    
    # Verify all shifts
    cur.execute("""
        SELECT shift_code, shift_name, start_time, end_time, is_active
        FROM historian_meta.shifts
        ORDER BY start_time
    """)
    
    print("✅ Shift times updated successfully!")
    print("\nCurrent shift configuration:")
    print("=" * 70)
    for row in cur.fetchall():
        code, name, start, end, active = row
        status = "✓" if active else "✗"
        print(f"{status} {code}: {name:30s} {start} - {end}")
    
    cur.close()
    conn.close()
    print("\n✅ Database connection closed")
    
except Exception as e:
    print(f"❌ Error: {e}")
