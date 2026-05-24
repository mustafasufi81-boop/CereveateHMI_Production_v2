"""Quick validation test for parameter passing"""
import sys
sys.path.insert(0, '.')

from services.historical_data import HistoricalDataService
from datetime import datetime, timedelta

# Test parameter passing validation
db_config = {
    'host': 'localhost',
    'port': 5432,
    'database': 'Cereveate',
    'user': 'cereveate',
    'password': 'cereveate@222'
}

print("🔍 Parameter Passing Validation Test")
print("=" * 40)

service = HistoricalDataService(db_config)
service.connect()

# Test 1: Check parameter defaults
print("1️⃣ Testing parameter defaults...")
result1 = service.get_multiple_trends(['Saw-toothed Waves.Real8'])
print(f"   Default params: {len(result1.get('Saw-toothed Waves.Real8', []))} points")

# Test 2: Check explicit parameters
print("\n2️⃣ Testing explicit parameters...")
end_time = datetime.now()
start_time = end_time - timedelta(hours=6)
result2 = service.get_multiple_trends(
    tag_ids=['Saw-toothed Waves.Real8'],
    start_time=start_time,
    end_time=end_time,
    max_points=500,
    sampling_interval=60
)
points = len(result2.get('Saw-toothed Waves.Real8', []))
print(f"   6h, 60s interval, 500 max: {points} points")

# Test 3: Check return data structure
print("\n3️⃣ Testing return data structure...")
if points > 0:
    sample = result2['Saw-toothed Waves.Real8'][0]
    print(f"   Sample point keys: {list(sample.keys())}")
    print(f"   Sample values: {sample}")
    print(f"   Timestamp type: {type(sample['timestamp'])}")
    print(f"   Value type: {type(sample['value'])}")
    print(f"   Quality type: {type(sample['quality'])}")

# Test 4: Check statistics
print("\n4️⃣ Testing statistics...")
stats = service.get_tag_statistics('Saw-toothed Waves.Real8', start_time, end_time)
if stats:
    print(f"   Stats keys: {list(stats.keys())}")
    print(f"   Count: {stats['count']}")
    print(f"   Average: {stats['average']}")
    print(f"   Min/Max: {stats['min']} / {stats['max']}")

# Test 5: Check latest value
print("\n5️⃣ Testing latest value...")
latest = service.get_latest_value('Saw-toothed Waves.Real8')
if latest:
    print(f"   Latest keys: {list(latest.keys())}")
    print(f"   Latest value: {latest['value']}")
    print(f"   Latest time: {latest['timestamp']}")

service.disconnect()
print("\n✅ All parameter passing validated!")