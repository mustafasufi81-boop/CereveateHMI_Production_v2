"""
Test what the Flask API actually returns in JSON format
"""
import psycopg2
import json
from flask import Flask, jsonify
from datetime import datetime

app = Flask(__name__)

# Load config
with open('config.json', 'r') as f:
    config = json.load(f)

# Connect to database
conn = psycopg2.connect(
    host=config['database']['host'],
    database=config['database']['database'],
    user=config['database']['user'],
    password=config['database']['password'],
    port=config['database']['port']
)

cursor = conn.cursor()

# Get sample record
cursor.execute("""
SELECT 
    time as timestamp,
    tag_id,
    value_num as value,
    quality
FROM historian_raw.historian_timeseries
WHERE tag_id = 'Welding_Current_A'
ORDER BY time DESC
LIMIT 1
""")

row = cursor.fetchone()
timestamp_obj, tag_id, value, quality = row

print("=" * 100)
print("FLASK JSON SERIALIZATION TEST")
print("=" * 100)

print(f"\n1. Database returns (Python datetime object):")
print(f"   Type: {type(timestamp_obj)}")
print(f"   Value: {timestamp_obj}")
print(f"   Microseconds property: {timestamp_obj.microsecond}")

print(f"\n2. Python .isoformat() conversion:")
iso_string = timestamp_obj.isoformat()
print(f"   Type: {type(iso_string)}")
print(f"   Value: {iso_string}")

print(f"\n3. Flask jsonify() conversion:")
# Create a dict like the API returns
data_dict = {
    'timestamp': timestamp_obj,
    'tag_id': tag_id,
    'value': value,
    'quality': quality
}

# Test jsonify
with app.app_context():
    response = jsonify(data_dict)
    json_string = response.get_data(as_text=True)
    
    print(f"   Raw JSON string from Flask:")
    print(f"   {json_string}")
    
    # Parse it back
    parsed = json.loads(json_string)
    print(f"\n4. Parsed JSON (what JavaScript receives):")
    print(f"   timestamp value: {parsed['timestamp']}")
    print(f"   timestamp type: {type(parsed['timestamp'])}")

print("\n" + "=" * 100)
print("JAVASCRIPT PARSING SIMULATION")
print("=" * 100)

# Simulate what JavaScript does
js_timestamp_string = parsed['timestamp']
print(f"\n1. JavaScript receives string: '{js_timestamp_string}'")

# Check if it has decimal part
if '.' in js_timestamp_string:
    parts = js_timestamp_string.split('.')
    decimal_part = parts[1]
    print(f"2. Split by '.': decimal part = '{decimal_part}'")
    
    # Remove timezone
    micros = decimal_part.split('+')[0].split('-')[0].split('Z')[0]
    print(f"3. After removing timezone: '{micros}'")
    
    # Pad to 6 digits
    microseconds = micros.ljust(6, '0')
    print(f"4. Padded to 6 digits: '{microseconds}'")
else:
    print("❌ NO DECIMAL PART FOUND!")
    microseconds = '000000'

print(f"\n5. Final UI display would show: YYYY-MM-DD HH:MM:SS.{microseconds}")

# Test with actual datetime parsing
print("\n" + "=" * 100)
print("TESTING DATETIME OBJECT DIRECTLY (NO JSON)")
print("=" * 100)

# What if we format the datetime directly in Python?
print(f"\nDirect format: {timestamp_obj.strftime('%Y-%m-%d %H:%M:%S')}.{str(timestamp_obj.microsecond).zfill(6)}")

cursor.close()
conn.close()
