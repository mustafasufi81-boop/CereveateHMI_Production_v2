import psycopg2
import os
import sys

# Safe parameterized insert for TY1101A into historian_meta.tag_master
# Configure connection via environment or defaults
DB_HOST = os.environ.get('PGHOST', 'localhost')
DB_PORT = os.environ.get('PGPORT', '5432')
# Using Historian DB settings from appsettings.json
DB_NAME = os.environ.get('PGDATABASE', 'Automation_DB')
DB_USER = os.environ.get('PGUSER', 'cereveate')
DB_PASS = os.environ.get('PGPASSWORD', 'cereveate@222')

conn = None
try:
    conn = psycopg2.connect(host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASS)
    cur = conn.cursor()

    insert_sql = '''
    INSERT INTO historian_meta.tag_master (
        tag_id, tag_name, description, plant, area, equipment,
        data_type, eng_unit, db_logging_interval_ms, logging_interval_ms,
        enabled, server_progid, plc_port, created_by, created_at,
        deadband_value, deadband_enabled
    ) VALUES (
        %(tag_id)s, %(tag_name)s, %(description)s, %(plant)s, %(area)s, %(equipment)s,
        %(data_type)s, %(eng_unit)s, %(db_logging_interval_ms)s, %(logging_interval_ms)s,
        %(enabled)s, %(server_progid)s, %(plc_port)s, %(created_by)s, NOW(),
        %(deadband_value)s, %(deadband_enabled)s
    )
    ON CONFLICT (tag_id) DO UPDATE SET
        tag_name = EXCLUDED.tag_name,
        description = EXCLUDED.description,
        plant = EXCLUDED.plant,
        area = EXCLUDED.area,
        equipment = EXCLUDED.equipment,
        data_type = EXCLUDED.data_type,
        eng_unit = EXCLUDED.eng_unit,
        db_logging_interval_ms = EXCLUDED.db_logging_interval_ms,
        logging_interval_ms = EXCLUDED.logging_interval_ms,
        enabled = EXCLUDED.enabled,
        server_progid = EXCLUDED.server_progid,
        plc_port = EXCLUDED.plc_port,
        deadband_value = EXCLUDED.deadband_value,
        deadband_enabled = EXCLUDED.deadband_enabled,
        created_by = EXCLUDED.created_by;
    '''

    params = {
        'tag_id': 'TY1101A',
        'tag_name': 'TY1101A Temperature',
        'description': 'Temperature sensor TY1101A',
        'plant': 'PlantA',
        'area': 'AreaA',
        'equipment': 'TY1101A_Vessel',
        'data_type': 'double',
        'eng_unit': 'C',
        'db_logging_interval_ms': 1000,
        'logging_interval_ms': 1000,
        'enabled': True,
        'server_progid': 'Rockwel_PLC_001',
        'plc_port': 44818,
        'created_by': 'admin',
        'deadband_value': 0.0,
        'deadband_enabled': False
    }

    cur.execute('BEGIN')
    cur.execute(insert_sql, params)
    cur.execute("SELECT tag_id, tag_name, server_progid, enabled, db_logging_interval_ms, deadband_value FROM historian_meta.tag_master WHERE tag_id = %s", (params['tag_id'],))
    row = cur.fetchone()
    conn.commit()
    if row:
        print('Inserted/Updated row:')
        print(row)
    else:
        print('No row returned after insert (unexpected)')

except Exception as e:
    if conn:
        conn.rollback()
    print('Error:', e)
    sys.exit(2)
finally:
    if conn:
        conn.close()
