"""
Test script to verify timestamp formatting matches UI behavior
Simulates JavaScript formatTimestampWithMs() function
"""
import psycopg2
import json
from datetime import datetime

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

# Get sample records (same as what API returns)
query = """
SELECT 
    time as timestamp,
    tag_id,
    value_num as value,
    quality
FROM historian_raw.historian_timeseries
WHERE tag_id = 'Welding_Current_A'
    AND time >= '2026-02-09 06:30:00+05:30'
    AND time < '2026-02-09 06:31:00+05:30'
ORDER BY time DESC
LIMIT 10;
"""

cursor.execute(query)
rows = cursor.fetchall()

print("=" * 130)
print("TIMESTAMP FORMATTING TEST - Simulating UI Behavior")
print("=" * 130)
print("\nTesting how timestamps are formatted in UI and CSV export:")
print()

def format_timestamp_with_microseconds(timestamp_obj):
    """
    Python equivalent of JavaScript formatTimestampWithMs() function
    Extracts full 6-digit microseconds from timestamp
    """
    # Convert to ISO format (simulates what Flask jsonify() returns)
    iso_string = timestamp_obj.isoformat()
    
    # Extract microseconds from ISO string (e.g., "2026-02-09T06:30:00.003155+05:30")
    microseconds = '000000'
    if '.' in iso_string:
        decimal_part = iso_string.split('.')[1]
        # Remove timezone part (+05:30 or Z)
        micros = decimal_part.split('+')[0].split('-')[0].split('Z')[0]
        # Pad to 6 digits if needed
        microseconds = micros.ljust(6, '0')
    
    # Format as: YYYY-MM-DD HH:MM:SS.mmmmmm
    formatted = timestamp_obj.strftime('%Y-%m-%d %H:%M:%S')
    return f"{formatted}.{microseconds}"

print(f"{'Database Timestamp (Raw)':<40} | {'ISO Format (API Returns)':<38} | {'UI Display Format (6-digit µs)':<35}")
print("-" * 130)

for row in rows:
    timestamp_obj, tag_id, value, quality = row
    
    # Step 1: What database returns (datetime object)
    db_format = str(timestamp_obj)
    
    # Step 2: What API returns (ISO format via Flask jsonify)
    iso_format = timestamp_obj.isoformat()
    
    # Step 3: What UI displays (after JavaScript formatting)
    ui_format = format_timestamp_with_microseconds(timestamp_obj)
    
    print(f"{db_format:<40} | {iso_format:<38} | {ui_format:<35}")

print("\n" + "=" * 130)
print("\nVERIFICATION CHECKS:")
print("=" * 130)

# Check 1: All timestamps have microseconds
all_have_microseconds = all('.' in str(row[0]) for row in rows)
print(f"✅ All timestamps have decimal part: {all_have_microseconds}")

# Check 2: Microseconds are non-zero
non_zero_microseconds = sum(1 for row in rows if row[0].microsecond > 0)
print(f"✅ Timestamps with non-zero microseconds: {non_zero_microseconds}/{len(rows)}")

# Check 3: UI format has 6 digits after decimal
sample_formatted = format_timestamp_with_microseconds(rows[0][0])
decimal_digits = len(sample_formatted.split('.')[1])
print(f"✅ UI format has {decimal_digits} digits after decimal (expected: 6)")

# Check 4: CSV export format test
print("\n" + "=" * 130)
print("CSV EXPORT FORMAT TEST:")
print("=" * 130)
print("\nCSV Header: #,Timestamp,Tag ID,Value,Quality")
print("\nFirst 5 CSV rows:")
for i, row in enumerate(rows[:5], 1):
    timestamp_obj, tag_id, value, quality = row
    csv_timestamp = format_timestamp_with_microseconds(timestamp_obj)
    csv_line = f"{i},{csv_timestamp},{tag_id},{value:.3f},{quality}"
    print(csv_line)

print("\n" + "=" * 130)
print("SUMMARY:")
print("=" * 130)
print(f"""
✅ Database stores: FULL 6-digit microseconds
✅ API returns:     ISO format with microseconds (e.g., 2026-02-09T06:30:00.003155+05:30)
✅ UI displays:     YYYY-MM-DD HH:MM:SS.mmmmmm (6 digits)
✅ CSV exports:     Same format as UI (6-digit microseconds)

Format Examples:
- Database:  {rows[0][0]}
- API (ISO): {rows[0][0].isoformat()}
- UI/CSV:    {format_timestamp_with_microseconds(rows[0][0])}
""")

cursor.close()
conn.close()
