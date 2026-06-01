import psycopg2
import requests

print("=" * 80)
print("CHECKING LIVE TAG VALUES")
print("=" * 80)

# Check database for recent values
print("\n[1] Database - Last 5 tag updates:")
try:
    conn = psycopg2.connect(
        host="localhost", port=5432, 
        database="Automation_DB", user="cereveate", password="cereveate@222"
    )
    cur = conn.cursor()
    cur.execute("""
        SELECT tag_id, time, value 
        FROM historian_raw.historian_timeseries 
        WHERE time > NOW() - INTERVAL '30 seconds'
        ORDER BY time DESC 
        LIMIT 5
    """)
    rows = cur.fetchall()
    if rows:
        for tag_id, time, value in rows:
            print(f"  {tag_id}: {time} = {value}")
    else:
        print("  ❌ NO DATA in last 30 seconds!")
    cur.close()
    conn.close()
except Exception as e:
    print(f"  ❌ Error: {e}")

# Check MQTT live cache
print("\n[2] HMI Live Cache - Sample tags:")
try:
    response = requests.get("http://localhost:8090/api/mqtt/plcs/Rockwel_PLC_001/tags", timeout=5)
    data = response.json()
    tags = data.get('tags', [])
    print(f"  Total tags available: {len(tags)}")
    for tag in tags[:3]:
        tag_name = tag.get('tag_name', 'Unknown')
        value = tag.get('value', 'N/A')
        timestamp = tag.get('timestamp', 'N/A')
        print(f"  {tag_name}: value={value}, timestamp={timestamp}")
except Exception as e:
    print(f"  ❌ Error: {e}")

print("\n" + "=" * 80)
