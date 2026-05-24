import psycopg2
from pycomm3 import LogixDriver

# Database connection
conn = psycopg2.connect(
    host='192.168.0.120',
    port=5432,
    database='Cereveate',
    user='postgres',
    password='Sh@hb@z9643'
)

cur = conn.cursor()

# Get welding parameter tags
cur.execute("""
    SELECT tag_id, tag_name 
    FROM historian_meta.tag_master 
    WHERE tag_id IN ('Pipe_Id', 'WPS_ID', 'Joint_Id', 'Arc', 'Power', 'Welding_Current_A', 'Welding_Voltage_V')
    ORDER BY tag_id
""")

tags = cur.fetchall()
print("Tags from database:")
for tag_id, tag_name in tags:
    print(f"  {tag_id} -> {tag_name}")

# Try to read directly from PLC
print("\n\nReading from PLC (192.168.0.20/1,0):")
with LogixDriver('192.168.0.20/1,0') as plc:
    for tag_id, tag_name in tags:
        try:
            result = plc.read(tag_id)
            print(f"  {tag_id}: value={result.value}, error={result.error}")
        except Exception as e:
            print(f"  {tag_id}: ERROR - {e}")

cur.close()
conn.close()
