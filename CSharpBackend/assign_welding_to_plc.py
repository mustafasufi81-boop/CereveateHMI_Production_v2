import psycopg2

conn = psycopg2.connect(
    host="localhost",
    database="Cereveate",
    user="cereveate",
    password="cereveate@222"
)

cur = conn.cursor()

print("\n" + "="*80)
print("ASSIGNING WELDING TAGS TO ROCKWELL PLC")
print("="*80)

welding_tags = [
    'Welding_Current_A',
    'Welding_Voltage_V',
    'Arc',
    'Power',
    'Pipe_Id',
    'Joint_Id',
    'Welder_id',
    'WPS_ID',
    'sim_step'
]

try:
    # Update welding tags to use Rockwell PLC
    update_sql = """
        UPDATE historian_meta.tag_master
        SET 
            server_progid = 'Rockwel_PLC_001',
            plc_protocol = 'Rockwell',
            plc_ip_address = '192.168.0.20',
            plc_port = 44818,
            plc_type = 'ControlLogix',
            plc_path = '1,0',
            plc_timeout_ms = 3000,
            plc_polling_interval_ms = 1000,
            use_connected_messaging = true
        WHERE tag_id = %s
    """
    
    updated = 0
    for tag in welding_tags:
        cur.execute(update_sql, (tag,))
        if cur.rowcount > 0:
            print(f"✅ Assigned {tag} to Rockwel_PLC_001")
            updated += 1
        else:
            print(f"❌ Tag not found: {tag}")
    
    conn.commit()
    
    print("\n" + "="*80)
    print(f"SUCCESS: Assigned {updated}/9 welding tags to Rockwel_PLC_001")
    print("="*80)
    
    # Verify
    print("\n4. Verification - Tags per PLC now:")
    cur.execute("""
        SELECT 
            server_progid,
            plc_ip_address,
            COUNT(*) as tag_count,
            COUNT(*) FILTER (WHERE enabled = true) as enabled_count
        FROM historian_meta.tag_master
        WHERE server_progid IS NOT NULL
        GROUP BY server_progid, plc_ip_address
        ORDER BY tag_count DESC
    """)
    
    print(f"\n{'PLC ProgID':<30} | {'IP Address':<15} | {'Total Tags':<12} | {'Enabled Tags'}")
    print("-" * 80)
    
    for row in cur.fetchall():
        plc, ip, total_tags, enabled_tags = row
        ip_str = ip if ip else "N/A"
        print(f"{plc:<30} | {ip_str:<15} | {total_tags:<12} | {enabled_tags}")
    
    print("\n✅ Rockwel_PLC_001 should now have 41 tags (32 + 9 welding tags)")
    print("✅ Restart C# backend to reload configuration")
    print("="*80)
    
except Exception as e:
    conn.rollback()
    print(f"\n❌ ERROR: {str(e)}")
finally:
    cur.close()
    conn.close()
