import psycopg2
import os
import sys
import json

# Load user-provided JSON (we'll override PLC IP to the value requested)
USER_JSON = os.path.join(os.path.dirname(__file__), 'TY1101A_user.json')

DB_HOST = os.environ.get('PGHOST', 'localhost')
DB_PORT = os.environ.get('PGPORT', '5432')
DB_NAME = os.environ.get('PGDATABASE', 'Automation_DB')
DB_USER = os.environ.get('PGUSER', 'cereveate')
DB_PASS = os.environ.get('PGPASSWORD', 'cereveate@222')

def load_and_prepare():
    with open(USER_JSON, 'r', encoding='utf-8') as f:
        obj = json.load(f)
    # Apply the PLC IP correction the user requested
    obj['plc_ip_address'] = '192.168.0.20'
    # Ensure server_progid links to Rockwell PLC (previous instruction)
    if 'server_progid' not in obj or not obj.get('server_progid'):
        obj['server_progid'] = 'Rockwel_PLC_001'
    # Ensure required non-null DB columns are present
    if 'db_logging_interval_ms' not in obj or obj.get('db_logging_interval_ms') is None:
        # Use logging_interval_ms if present, else fallback to 1000
        obj['db_logging_interval_ms'] = obj.get('logging_interval_ms', 1000)
    if 'enabled' not in obj:
        obj['enabled'] = True
    return obj


def main():
    obj = load_and_prepare()
    conn = None
    try:
        conn = psycopg2.connect(host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASS)
        cur = conn.cursor()

        insert_sql = '''
        INSERT INTO historian_meta.tag_master (
            tag_id, tag_name, description, plant, area, equipment,
            data_type, eng_unit, db_logging_interval_ms, logging_interval_ms,
            enabled, db_table_name, mapping_version, created_by, created_at,
            deadband_enabled, deadband_value,
            alarm_enabled, alarm_h_limit, alarm_hh_limit, alarm_l_limit, alarm_ll_limit,
            plc_ip_address, plc_port, plc_type, sub_equipment, components,
            server_progid, process_unit, equipment_criticality, alarm_priority, alarm_deadband,
            plc_path, plc_timeout_ms, plc_polling_interval_ms, use_connected_messaging, plc_slot
        ) VALUES (
            %(tag_id)s, %(tag_name)s, %(description)s, %(plant)s, %(area)s, %(equipment)s,
            %(data_type)s, %(eng_unit)s, %(db_logging_interval_ms)s, %(logging_interval_ms)s,
            %(enabled)s, %(db_table_name)s, %(mapping_version)s, %(created_by)s, NOW(),
            %(deadband_enabled)s, %(deadband_value)s,
            %(alarm_enabled)s, %(alarm_h_limit)s, %(alarm_hh_limit)s, %(alarm_l_limit)s, %(alarm_ll_limit)s,
            %(plc_ip_address)s, %(plc_port)s, %(plc_type)s, %(sub_equipment)s, %(components)s,
            %(server_progid)s, %(process_unit)s, %(equipment_criticality)s, %(alarm_priority)s, %(alarm_deadband)s,
            %(plc_path)s, %(plc_timeout_ms)s, %(plc_polling_interval_ms)s, %(use_connected_messaging)s, %(plc_slot)s
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
            db_table_name = EXCLUDED.db_table_name,
            mapping_version = EXCLUDED.mapping_version,
            created_by = EXCLUDED.created_by,
            deadband_enabled = EXCLUDED.deadband_enabled,
            deadband_value = EXCLUDED.deadband_value,
            alarm_enabled = EXCLUDED.alarm_enabled,
            alarm_h_limit = EXCLUDED.alarm_h_limit,
            alarm_hh_limit = EXCLUDED.alarm_hh_limit,
            alarm_l_limit = EXCLUDED.alarm_l_limit,
            alarm_ll_limit = EXCLUDED.alarm_ll_limit,
            plc_ip_address = EXCLUDED.plc_ip_address,
            plc_port = EXCLUDED.plc_port,
            plc_type = EXCLUDED.plc_type,
            sub_equipment = EXCLUDED.sub_equipment,
            components = EXCLUDED.components,
            server_progid = EXCLUDED.server_progid,
            process_unit = EXCLUDED.process_unit,
            equipment_criticality = EXCLUDED.equipment_criticality,
            alarm_priority = EXCLUDED.alarm_priority,
            alarm_deadband = EXCLUDED.alarm_deadband,
            plc_path = EXCLUDED.plc_path,
            plc_timeout_ms = EXCLUDED.plc_timeout_ms,
            plc_polling_interval_ms = EXCLUDED.plc_polling_interval_ms,
            use_connected_messaging = EXCLUDED.use_connected_messaging,
            plc_slot = EXCLUDED.plc_slot;
        '''

        params = {
            'tag_id': obj.get('tag_id'),
            'tag_name': obj.get('tag_name'),
            'description': obj.get('description'),
            'plant': obj.get('plant'),
            'area': obj.get('area'),
            'equipment': obj.get('equipment'),
            'data_type': obj.get('data_type'),
            'eng_unit': obj.get('eng_unit'),
            'db_logging_interval_ms': obj.get('db_logging_interval_ms'),
            'logging_interval_ms': obj.get('logging_interval_ms'),
            'enabled': obj.get('enabled'),
            'db_table_name': obj.get('db_table_name', 'historian_raw.historian_timeseries'),
            'mapping_version': obj.get('mapping_version', 1),
            'created_by': obj.get('created_by', 'admin'),
            'deadband_enabled': obj.get('deadband_enabled', False),
            'deadband_value': obj.get('deadband_value'),
            'alarm_enabled': obj.get('alarm_enabled', False),
            'alarm_h_limit': obj.get('alarm_h_limit'),
            'alarm_hh_limit': obj.get('alarm_hh_limit'),
            'alarm_l_limit': obj.get('alarm_l_limit'),
            'alarm_ll_limit': obj.get('alarm_ll_limit'),
            'plc_ip_address': obj.get('plc_ip_address'),
            'plc_port': obj.get('plc_port'),
            'plc_type': obj.get('plc_type'),
            'sub_equipment': obj.get('sub_equipment'),
            'components': obj.get('components'),
            'server_progid': obj.get('server_progid'),
            'process_unit': obj.get('process_unit'),
            'equipment_criticality': obj.get('equipment_criticality'),
            'alarm_priority': obj.get('alarm_priority'),
            'alarm_deadband': obj.get('alarm_deadband'),
            'plc_path': obj.get('plc_path'),
            'plc_timeout_ms': obj.get('plc_timeout_ms'),
            'plc_polling_interval_ms': obj.get('plc_polling_interval_ms'),
            'use_connected_messaging': obj.get('use_connected_messaging'),
            'plc_slot': obj.get('plc_slot')
        }

        cur.execute('BEGIN')
        cur.execute(insert_sql, params)
        cur.execute('SELECT tag_id, tag_name, plant, area, equipment, data_type, plc_ip_address, plc_port FROM historian_meta.tag_master WHERE tag_id = %s', (params['tag_id'],))
        row = cur.fetchone()
        conn.commit()
        if row:
            print('Inserted/Updated:')
            print(row)
        else:
            print('Insert completed but could not verify row')

    except Exception as e:
        if conn:
            conn.rollback()
        print('Error:', e)
        sys.exit(2)
    finally:
        if conn:
            conn.close()


if __name__ == '__main__':
    main()
