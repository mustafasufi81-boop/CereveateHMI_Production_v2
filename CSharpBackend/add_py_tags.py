import psycopg2

c = psycopg2.connect('host=localhost dbname=Automation_DB user=cereveate password=cereveate@222')
cur = c.cursor()

# New tags — PLC config identical to TY1101A (same server_progid, protocol, port, path, type)
tags = [
    {
        'tag_id': 'PY1101A', 'tag_name': 'PY1101A',
        'description': 'FILTER INLET PRESSURE 1#',
        'equipment': 'DUCT', 'sub_equipment': 'DUCT INLET-1', 'components': 'PRESSURE 1#',
        'eng_unit': 'KPA', 'data_type': 'double',
        'alarm_h_limit': 1.5, 'alarm_hh_limit': None, 'alarm_l_limit': 0.7, 'alarm_ll_limit': None,
        'alarm_priority': 3, 'plc_ip_address': '192.168.0.20',
    },
    {
        'tag_id': 'PY1101B', 'tag_name': 'PY1101B',
        'description': 'FILTER INLET PRESSURE 2#',
        'equipment': 'DUCT', 'sub_equipment': 'DUCT INLET-2', 'components': 'PRESSURE 2#',
        'eng_unit': 'KPA', 'data_type': 'double',
        'alarm_h_limit': 1.5, 'alarm_hh_limit': None, 'alarm_l_limit': 0.7, 'alarm_ll_limit': None,
        'alarm_priority': 3, 'plc_ip_address': '192.168.0.20',
    },
    {
        'tag_id': 'PY1103A', 'tag_name': 'PY1103A',
        'description': 'ROOTS FAN OUTLET OF PRESSURE #1',
        'equipment': 'BLOWER', 'sub_equipment': 'AIR ROOT BLOWER-1', 'components': 'OUTLET PRESSURE #1',
        'eng_unit': 'KPA', 'data_type': 'double',
        'alarm_h_limit': 20.7, 'alarm_hh_limit': 60.0, 'alarm_l_limit': 14.5, 'alarm_ll_limit': 8.0,
        'alarm_priority': 2, 'plc_ip_address': '192.168.0.20',
    },
    {
        'tag_id': 'PY1103B', 'tag_name': 'PY1103B',
        'description': 'ROOTS FAN OUTLET OF PRESSURE #2',
        'equipment': 'BLOWER', 'sub_equipment': 'AIR ROOT BLOWER-2', 'components': 'OUTLET PRESSURE #2',
        'eng_unit': 'KPA', 'data_type': 'double',
        'alarm_h_limit': 20.7, 'alarm_hh_limit': 60.0, 'alarm_l_limit': 14.5, 'alarm_ll_limit': 8.0,
        'alarm_priority': 2, 'plc_ip_address': '192.168.0.20',
    },
]

for t in tags:
    cur.execute("""
        INSERT INTO historian_meta.tag_master (
            tag_id, tag_name, description,
            plant, area, equipment, sub_equipment, components,
            data_type, eng_unit,
            db_logging_interval_ms, logging_interval_ms, enabled,
            db_table_name, mapping_version,
            alarm_enabled, alarm_h_limit, alarm_hh_limit, alarm_l_limit, alarm_ll_limit,
            alarm_priority, alarm_onset_delay_s,
            server_progid,
            plc_ip_address, plc_port, plc_protocol, plc_path, plc_type,
            plc_timeout_ms, plc_polling_interval_ms,
            equipment_criticality, is_trip_initiator,
            created_by
        ) VALUES (
            %(tag_id)s, %(tag_name)s, %(description)s,
            'FTP-1', 'POTLINE', %(equipment)s, %(sub_equipment)s, %(components)s,
            %(data_type)s, %(eng_unit)s,
            1000, 1000, true,
            'historian_raw.historian_timeseries', 1,
            true, %(alarm_h_limit)s, %(alarm_hh_limit)s, %(alarm_l_limit)s, %(alarm_ll_limit)s,
            %(alarm_priority)s, 0,
            'Rockwel_PLC_001',
            %(plc_ip_address)s, 44818, 'Rockwell', '1,0', 'ControlLogix',
            3000, 1000,
            3, false,
            'admin'
        )
        ON CONFLICT (tag_id) DO UPDATE SET
            description       = EXCLUDED.description,
            equipment         = EXCLUDED.equipment,
            sub_equipment     = EXCLUDED.sub_equipment,
            components        = EXCLUDED.components,
            data_type         = EXCLUDED.data_type,
            eng_unit          = EXCLUDED.eng_unit,
            alarm_h_limit     = EXCLUDED.alarm_h_limit,
            alarm_hh_limit    = EXCLUDED.alarm_hh_limit,
            alarm_l_limit     = EXCLUDED.alarm_l_limit,
            alarm_ll_limit    = EXCLUDED.alarm_ll_limit,
            alarm_priority    = EXCLUDED.alarm_priority,
            plc_ip_address    = EXCLUDED.plc_ip_address,
            config_updated_at = NOW()
    """, t)
    print(f"  Upserted {t['tag_id']}: {t['description']}")

c.commit()

# Verify
cur.execute("""
    SELECT tag_id, description, eng_unit,
           alarm_h_limit, alarm_hh_limit, alarm_l_limit, alarm_ll_limit, alarm_priority,
           plc_ip_address, server_progid, plc_port, plc_path
    FROM historian_meta.tag_master
    WHERE tag_id IN ('PY1101A','PY1101B','PY1103A','PY1103B')
    ORDER BY tag_id
""")
print("\nVerification:")
for r in cur.fetchall():
    print(f"  {r[0]}: {r[1]} | unit={r[2]} | H={r[3]} HH={r[4]} L={r[5]} LL={r[6]} pri={r[7]} | ip={r[8]} plc={r[9]}:{r[10]} path={r[11]}")

c.close()
print("\nDone.")
