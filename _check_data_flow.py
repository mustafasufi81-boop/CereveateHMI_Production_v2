import requests
import json

print("=" * 80)
print("CHECKING DATA FLOW")
print("=" * 80)

# Check C# backend PLC connections
print("\n[1] C# Backend - PLC Connections:")
try:
    response = requests.get("http://localhost:5001/api/plc/connections", timeout=5)
    data = response.json()
    for conn in data.get('connections', []):
        print(f"  {conn['serverProgId']}: Connected={conn['isConnected']}, Tags={conn['tagCount']}, State={conn.get('state', 'N/A')}")
except Exception as e:
    print(f"  ❌ Error: {e}")

# Check Flask backend MQTT status
print("\n[2] Flask Backend - MQTT Status:")
try:
    response = requests.get("http://localhost:6001/api/system/health", timeout=5)
    data = response.json()
    print(f"  MQTT Connected: {data.get('mqtt_connected', False)}")
    print(f"  Database Connected: {data.get('database_connected', False)}")
except Exception as e:
    print(f"  ❌ Error: {e}")

# Check recent tag updates in database
print("\n[3] Database - Recent Tag Updates:")
try:
    import psycopg2
    conn = psycopg2.connect(
        host="localhost", port=5432, 
        database="Automation_DB", user="cereveate", password="cereveate@222"
    )
    cur = conn.cursor()
    cur.execute("""
        SELECT tag_id, MAX(time) as last_update 
        FROM historian_raw.historian_timeseries 
        WHERE time > NOW() - INTERVAL '5 minutes'
        GROUP BY tag_id 
        ORDER BY last_update DESC 
        LIMIT 5
    """)
    rows = cur.fetchall()
    if rows:
        for tag_id, last_update in rows:
            print(f"  {tag_id}: {last_update}")
    else:
        print("  ❌ NO RECENT DATA in last 5 minutes!")
    cur.close()
    conn.close()
except Exception as e:
    print(f"  ❌ Error: {e}")

print("\n" + "=" * 80)
