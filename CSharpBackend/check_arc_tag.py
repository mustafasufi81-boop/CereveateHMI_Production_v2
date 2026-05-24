import psycopg2

conn = psycopg2.connect(
    host="localhost",
    database="Cereveate",
    user="cereveate",
    password="cereveate@222"
)

cur = conn.cursor()

# Check Arc tag configuration
cur.execute("""
    SELECT tag_id, data_type, plc_ip_address, enabled, server_progid
    FROM historian_meta.tag_master
    WHERE tag_id = 'Arc'
""")

row = cur.fetchone()
if row:
    print("\n" + "="*60)
    print("ARC TAG CONFIGURATION IN DATABASE")
    print("="*60)
    print(f"Tag ID: {row[0]}")
    print(f"Data Type: {row[1]}")
    print(f"PLC Address: {row[2]}")
    print(f"Enabled: {row[3]}")
    print(f"Server: {row[4]}")
    print("="*60)
else:
    print("❌ Arc tag not found!")

# Check what PLC Gateway is returning for Arc
import urllib.request
import json

print("\n" + "="*60)
print("ARC VALUE FROM PLC GATEWAY API")
print("="*60)

try:
    req = urllib.request.Request('http://127.0.0.1:5001/api/plc/values')
    with urllib.request.urlopen(req, timeout=3) as response:
        plc_data = json.loads(response.read().decode('utf-8'))
        if plc_data.get('success') and 'values' in plc_data:
            arc_tags = [v for v in plc_data['values'] if 'Arc' in v.get('tagName', '')]
            if arc_tags:
                for tag in arc_tags:
                    print(f"Tag Name: {tag.get('tagName')}")
                    print(f"Address: {tag.get('address')}")
                    print(f"Value: {tag.get('value')}")
                    print(f"Data Type: {tag.get('dataType')}")
                    print(f"Quality: {tag.get('quality')}")
                    print(f"PLC ID: {tag.get('plcId')}")
            else:
                print("❌ Arc tag not found in PLC values!")
        else:
            print("❌ PLC API returned error")
except Exception as e:
    print(f"❌ Error: {e}")

print("="*60)

cur.close()
conn.close()
