import psycopg2

conn = psycopg2.connect(host='localhost', port=5432, dbname='Automation_DB', user='cereveate', password='cereveate@222')
cur = conn.cursor()

cur.execute("SELECT tag_id, mapping_version, config_updated_at, created_at FROM historian_meta.tag_master WHERE tag_id IN ('PY1104','PY1105A')")
print('PRE-INSERT (should be empty):', cur.fetchall())

cur.execute("""
INSERT INTO historian_meta.tag_master (
    tag_id, tag_name, description, plant, area, equipment,
    sub_equipment, components, data_type, eng_unit,
    alarm_enabled, alarm_h_limit, alarm_hh_limit, alarm_l_limit, alarm_ll_limit,
    alarm_priority, alarm_deadband, equipment_criticality,
    db_logging_interval_ms, logging_interval_ms,
    deadband_enabled, deadband_value, enabled, db_table_name,
    server_progid, plc_ip_address, plc_port, plc_protocol,
    plc_path, plc_type, plc_timeout_ms, plc_polling_interval_ms,
    include_in_report, report_flag, created_by
) VALUES
    ('PY1104','PY1104','CHUTE  SILO FAN OUTLET OF PRESSURE','FTP-1','POTLINE','FAN',
     'AIRSLIDE FAN','OUTLET PRESSURE','double','KPA',
     TRUE, 9.0, 10.0, 6.0, 4.0,
     2, 1.0, 2,
     1000, 1000,
     FALSE, NULL, TRUE, 'historian_raw.historian_timeseries',
     'Rockwel_PLC_001','192.168.1.11',44818,'Rockwell',
     '1,0','ControlLogix',3000,1000,
     TRUE,TRUE,'excel_import'),
    ('PY1105A','PY1105A','FILTER AIR BAG OF PRESSURE #1','FTP-1','POTLINE','BAG HOUSE',
     'FILTER-1','PRESSURE #1','double','KPA',
     TRUE, 0.4, 0.6, 0.3, 0.15,
     2, 1.0, 2,
     1000, 1000,
     FALSE, NULL, TRUE, 'historian_raw.historian_timeseries',
     'Rockwel_PLC_001','192.168.1.11',44818,'Rockwell',
     '1,0','ControlLogix',3000,1000,
     TRUE,TRUE,'excel_import')
ON CONFLICT (tag_id) DO NOTHING
""")
conn.commit()
print(f'Rows inserted: {cur.rowcount}')

cur.execute("SELECT tag_id, mapping_version, config_updated_at, created_at FROM historian_meta.tag_master WHERE tag_id IN ('PY1104','PY1105A') ORDER BY tag_id")
rows = cur.fetchall()
print('\nPOST-INSERT:')
for r in rows:
    print(f'  tag_id={r[0]}  mapping_version={r[1]}  config_updated_at={r[2]}  created_at={r[3]}')

conn.close()
