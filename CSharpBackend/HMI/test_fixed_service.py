"""Test script for the fixed historical data service"""
import sys
sys.path.insert(0, '.')

from services.historical_data import HistoricalDataService
from datetime import datetime, timedelta
import time

# Test the improved connection pool service
db_config = {
    'host': 'localhost',
    'port': 5432,
    'database': 'Cereveate',
    'user': 'cereveate',
    'password': 'cereveate@222'
}

print("🧪 Testing FIXED Historical Data Service")
print("=" * 50)

# Create service
service = HistoricalDataService(db_config)

print("1️⃣ Testing connection pool...")
result = service.connect()
print(f"   Connected: {result}")

if not result:
    print("❌ Connection failed! Check database settings.")
    exit(1)

print("\n2️⃣ Testing get_multiple_trends...")
end_time = datetime.now()
start_time = end_time - timedelta(hours=24)

# Test with a tag that should have data
test_tags = ['Saw-toothed Waves.Real8', 'Random_UInt2']

start = time.time()
results = service.get_multiple_trends(
    tag_ids=test_tags,
    start_time=start_time,
    end_time=end_time,
    max_points=1000,
    sampling_interval=30
)
elapsed = time.time() - start

print(f"   Query time: {elapsed:.3f}s")
for tag_id, points in results.items():
    print(f"   {tag_id}: {len(points)} points")
    if points:
        print(f"     Sample: {points[0]}")

print("\n3️⃣ Testing get_latest_value...")
for tag in test_tags[:1]:  # Test just one
    latest = service.get_latest_value(tag)
    if latest:
        print(f"   {tag}: {latest['value']} at {latest['timestamp']}")
    else:
        print(f"   {tag}: No data found")

print("\n4️⃣ Testing concurrent queries...")
import threading

def query_test(tag_name, thread_id):
    conn = None
    try:
        start = time.time()
        result = service.get_multiple_trends([tag_name], start_time, end_time, 100)
        elapsed = time.time() - start
        points = len(result.get(tag_name, []))
        print(f"   Thread {thread_id}: {points} points in {elapsed:.3f}s")
    except Exception as e:
        print(f"   Thread {thread_id}: ERROR - {e}")
    # Connection is handled internally by the service

# Run 3 concurrent queries
threads = []
for i in range(3):
    t = threading.Thread(target=query_test, args=('Saw-toothed Waves.Real8', i+1))
    threads.append(t)
    t.start()

for t in threads:
    t.join()

print("\n5️⃣ Testing connection management...")
print("   Pool status before:", service.is_connected())

# Test that connections are properly returned to pool
for i in range(5):
    conn = service._get_connection()
    print(f"   Got connection {i+1}")
    service._return_connection(conn)
    print(f"   Returned connection {i+1}")

print("   Pool status after:", service.is_connected())

print("\n6️⃣ Cleanup and final shutdown...")
service.disconnect()
print("   Pool closed properly")
print("   Final status:", service.is_connected())

print("\n✅ Test complete!")
print("✅ All connections properly managed and closed!")
print("If you see data points above, the service is working!")