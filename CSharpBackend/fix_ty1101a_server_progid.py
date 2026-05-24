import psycopg2

conn = psycopg2.connect(host='localhost', port=5432, dbname='Automation_DB', user='cereveate', password='cereveate@222')
cur = conn.cursor()

# Show current state
cur.execute("SELECT tag_id, server_progid, enabled FROM historian_meta.tag_master WHERE tag_id = 'TY1101A'")
print('Current TY1101A:', cur.fetchone())

# Show all server_progids
cur.execute("SELECT server_progid, COUNT(*) FROM historian_meta.tag_master GROUP BY server_progid ORDER BY COUNT(*) DESC")
print('\nAll server_progids in tag_master:')
for r in cur.fetchall():
    print(' ', r)

# The TagPool log says active server is "Matrikon.OPC.Simulation.1" for OPC path
# BUT TY1101A is a Rockwell PLC tag - it must stay as Rockwel_PLC_001
# The REAL problem: the Rockwell PLC gateway worker never started because 
# appsettings.json PlcGateway Connections has PlcId "Rockwel_PLC_001" with old tags
# Let's check what PlcId the gateway is actually using

# Show appsettings PlcGateway section by checking plc-config.json if it exists
import os, json
config_paths = [
    r'c:\MQTT_Implemented_OPC\Copied_MQTT\BACKUP_BEFORE_HISTORICAL_20251117_225747 - Copy_backup_20251206\bin\Release\net8.0\win-x86\plc-config.json',
    r'c:\MQTT_Implemented_OPC\Copied_MQTT\BACKUP_BEFORE_HISTORICAL_20251117_225747 - Copy_backup_20251206\plc-config.json',
]
for p in config_paths:
    if os.path.exists(p):
        print(f'\nFound plc-config.json at: {p}')
        with open(p) as f:
            data = json.load(f)
        print(json.dumps(data, indent=2))

conn.close()
