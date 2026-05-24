"""
Test the custom jsonify function to verify microsecond preservation
"""
import json
from datetime import datetime
import psycopg2

# Load config
with open('config.json', 'r') as f:
    config = json.load(f)

# Custom jsonify simulation (same as in historian_query_tool_v2.py)
def custom_jsonify(data):
    """Custom jsonify that preserves datetime microseconds in ISO format"""
    def datetime_handler(obj):
        if isinstance(obj, datetime):
            # Return ISO format with full 6-digit microseconds
            return obj.isoformat()
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
    
    json_str = json.dumps(data, default=datetime_handler, ensure_ascii=False)
    return json_str

# Connect to database
conn = psycopg2.connect(
    host=config['database']['host'],
    database=config['database']['database'],
    user=config['database']['user'],
    password=config['database']['password'],
    port=config['database']['port']
)

cursor = conn.cursor()

# Get sample records (exactly as API does)
query = """
SELECT 
    time as timestamp,
    tag_id,
    value_num as value,
    quality
FROM historian_raw.historian_timeseries
WHERE tag_id = 'Welding_Current_A'
ORDER BY time DESC
LIMIT 5;
"""

cursor.execute(query)
rows = cursor.fetchall()

print("=" * 120)
print("FLASK CUSTOM JSONIFY TEST - Microsecond Preservation")
print("=" * 120)

# Simulate what the API endpoint does
api_response_data = []
for row in rows:
    timestamp_obj, tag_id, value, quality = row
    api_response_data.append({
        'timestamp': timestamp_obj,  # datetime object from PostgreSQL
        'tag_id': tag_id,
        'value': value,
        'quality': quality
    })

# Apply custom jsonify (same as Flask endpoint)
json_output = custom_jsonify({'data': api_response_data})

print("\n1. RAW DATABASE TIMESTAMPS:")
print("-" * 120)
for row in rows:
    timestamp_obj = row[0]
    print(f"   {timestamp_obj} (microseconds: {timestamp_obj.microsecond})")

print("\n2. AFTER CUSTOM JSONIFY (what API returns):")
print("-" * 120)
print(json_output[:500] + "...")  # First 500 chars

# Parse it back like JavaScript would
parsed = json.loads(json_output)

print("\n3. JAVASCRIPT RECEIVES (parsed JSON):")
print("-" * 120)
for i, record in enumerate(parsed['data'][:5], 1):
    timestamp_str = record['timestamp']
    print(f"   {i}. {timestamp_str}")
    
    # Simulate JavaScript extraction
    if '.' in timestamp_str:
        decimal_part = timestamp_str.split('.')[1]
        micros = decimal_part.split('+')[0].split('-')[0].split('Z')[0]
        microseconds = micros.ljust(6, '0')
        print(f"      → Extracted microseconds: {microseconds}")
    else:
        print(f"      → ❌ NO DECIMAL PART!")

print("\n" + "=" * 120)
print("VERIFICATION:")
print("=" * 120)

# Check all timestamps
all_have_decimals = all('.' in record['timestamp'] for record in parsed['data'])
all_non_zero = all(record['timestamp'].split('.')[1].split('+')[0] != '000000' 
                   for record in parsed['data'] if '.' in record['timestamp'])

print(f"✅ All timestamps have decimal part: {all_have_decimals}")
print(f"✅ All have non-zero microseconds: {all_non_zero}")

if all_have_decimals and all_non_zero:
    print("\n🎉 SUCCESS: Custom jsonify preserves full 6-digit microseconds!")
    print("   UI will now display: YYYY-MM-DD HH:MM:SS.mmmmmm")
else:
    print("\n❌ FAILED: Microseconds are lost or zero")

cursor.close()
conn.close()
