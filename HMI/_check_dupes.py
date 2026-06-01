import psycopg2, json
cfg=json.load(open('config.json'))
d=cfg['database']
c=psycopg2.connect(host=d['host'], port=d['port'], database=d['database'], user=d['user'], password=d['password'])
cur=c.cursor()
cur.execute("SELECT id, plant_code, area_code, plant, area, server_progid FROM historian_meta.plants_areas WHERE server_progid='Rockwel_PLC_001' AND is_active=true")
for row in cur.fetchall():
    print(row)
