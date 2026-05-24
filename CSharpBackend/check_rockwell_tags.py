import psycopg2
from tabulate import tabulate

# Connect to database
conn = psycopg2.connect(
    host='localhost',
    database='Cereveate',
    user='cereveate',
    password='cereveate@222'
)

cur = conn.cursor()

# Query Rockwell PLC tags
query = """
SELECT 
    tag_id, 
    tag_name, 
    server_progid, 
    data_type, 
    plc_ip_address,
    plc_port,
    enabled
FROM historian_meta.tag_master 
WHERE server_progid = 'Rockwel_PLC_001'
ORDER BY tag_id;
"""

cur.execute(query)
rows = cur.fetchall()

print(f"\n=== ROCKWELL PLC TAGS (server_progid = 'Rockwel_PLC_001') ===")
print(f"Total tags found: {len(rows)}\n")

if rows:
    headers = ['tag_id', 'tag_name', 'server_progid', 'data_type', 'plc_ip', 'port', 'enabled']
    print(tabulate(rows, headers=headers, tablefmt='grid'))
else:
    print("No tags found with server_progid = 'Rockwel_PLC_001'")

conn.close()
