"""
Verify production calculations
"""
import requests
import json

BASE_URL = "http://127.0.0.1:5002"

print("\n" + "="*80)
print("VERIFYING PRODUCTION CALCULATIONS")
print("="*80)

# Step 1: Get data
print("\n1️⃣  Getting data from API")
response = requests.get(f"{BASE_URL}/api/data", params={
    'start_date': '2025-10-21T20:00:00.000Z',
    'end_date': '2025-11-20T20:00:00.000Z',
    'tags': json.dumps(['TURBINE_LOADMW'])
})

data = response.json()
records = data['data']
print(f"✓ Got {len(records)} records")

# Step 2: Calculate current period average (what dashboard shows as "Today's Production")
load_values = []
for record in records:
    try:
        load_values.append(float(record['TURBINE_LOADMW']))
    except:
        pass

if load_values:
    current_avg = sum(load_values) / len(load_values)
    min_val = min(load_values)
    max_val = max(load_values)
    
    print(f"\n📊 CURRENT PERIOD STATISTICS:")
    print(f"   Total records: {len(load_values)}")
    print(f"   Average (Current Production): {current_avg:.2f} MW")
    print(f"   Min: {min_val:.2f} MW")
    print(f"   Max: {max_val:.2f} MW")
    print(f"   Range: {max_val - min_val:.2f} MW")

# Step 3: Calculate top 10% (Baseline)
sorted_values = sorted(load_values, reverse=True)
top_10_percent_count = max(1, int(len(sorted_values) * 0.10))
top_10_values = sorted_values[:top_10_percent_count]
baseline_avg = sum(top_10_values) / len(top_10_values)

print(f"\n📈 BASELINE (TOP 10%) STATISTICS:")
print(f"   Top 10% count: {top_10_percent_count}")
print(f"   Baseline average: {baseline_avg:.2f} MW")
print(f"   Top values range: {min(top_10_values):.2f} - {max(top_10_values):.2f} MW")

# Step 4: Get rated capacity from config
try:
    config_response = requests.get(f"{BASE_URL}/api/baseline/config?tag=TURBINE_LOADMW")
    if config_response.ok:
        config_data = config_response.json()
        rated_capacity = config_data.get('rated_capacity', 270)
    else:
        rated_capacity = 270
except:
    rated_capacity = 270

print(f"\n🎯 TARGET/BEST PERFORMANCE:")
print(f"   Rated Capacity: {rated_capacity} MW")

# Step 5: Calculate deltas
delta_from_baseline = abs(current_avg - baseline_avg)
delta_from_best = abs(rated_capacity - current_avg)

is_gain = current_avg > baseline_avg

print(f"\n📉 DELTA CALCULATIONS:")
print(f"   Current vs Baseline: {delta_from_baseline:.2f} MW ({'GAIN' if is_gain else 'LOSS'})")
print(f"   Current vs Best: {delta_from_best:.2f} MW (LOSS)")

# Step 6: Calculate utilization
utilization = (current_avg / rated_capacity) * 100 if rated_capacity > 0 else 0

print(f"\n⚡ UTILIZATION:")
print(f"   {current_avg:.2f} / {rated_capacity} × 100 = {utilization:.2f}%")

print("\n" + "="*80)
print("EXPECTED DASHBOARD VALUES:")
print("="*80)
print(f"Current Period Avg:  {current_avg:.2f} MW")
print(f"Baseline (Top 10%):  {baseline_avg:.2f} MW")
print(f"Best/Target:         {rated_capacity:.2f} MW")
print(f"Delta from Baseline: {delta_from_baseline:.2f} MW ({'Gain' if is_gain else 'Loss'})")
print(f"Loss from Best:      {delta_from_best:.2f} MW")
print(f"Utilization:         {utilization:.2f}%")
print("="*80 + "\n")
