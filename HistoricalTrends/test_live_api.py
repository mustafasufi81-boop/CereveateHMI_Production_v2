"""
Live API Testing Script - Tests actual Flask endpoints
Simulates what JavaScript does in the browser
"""
import requests
import json

BASE_URL = "http://127.0.0.1:5002/api/v1"

print("\n" + "="*80)
print("LIVE API ENDPOINT TESTING")
print("="*80)

# Sample data matching what JavaScript sends
sample_data = [
    {'Timestamp': '2025-11-20T10:00:00', 'TURBINE_LOADMW': 105.5, 'TOTAL_COAL_FLOW': 120.3},
    {'Timestamp': '2025-11-20T11:00:00', 'TURBINE_LOADMW': 108.2, 'TOTAL_COAL_FLOW': 122.1},
    {'Timestamp': '2025-11-20T12:00:00', 'TURBINE_LOADMW': 106.8, 'TOTAL_COAL_FLOW': 121.5},
    {'Timestamp': '2025-11-20T13:00:00', 'TURBINE_LOADMW': 107.3, 'TOTAL_COAL_FLOW': 121.8},
]

print("\n1️⃣  BASELINE ENDPOINT")
print("-" * 80)
response = requests.post(f"{BASE_URL}/baseline/calculate", json={
    'data': sample_data,
    'tag': 'TURBINE_LOADMW',
    'config': {
        'baseline_window': 30,
        'top_percentile': 90,
        'outlier_threshold': 3.0,
        'outlier_method': 'sigma',
        'min_data_points': 3
    }
})
print(f"Status: {response.status_code}")
if response.status_code == 200:
    baseline = response.json()
    print(f"✓ Fields: {list(baseline.keys())}")
    print(f"  value: {baseline.get('value')}")
    print(f"  std_dev: {baseline.get('std_dev')}")
    print(f"  sample_size: {baseline.get('sample_size')}")
    print(f"  valid_until: {baseline.get('valid_until')}")
    assert 'value' in baseline, "Missing 'value'"
    assert 'std_dev' in baseline, "Missing 'std_dev'"
    assert 'sample_size' in baseline, "Missing 'sample_size'"
    assert 'valid_until' in baseline, "Missing 'valid_until'"
else:
    print(f"❌ Error: {response.text}")
    exit(1)

print("\n2️⃣  EFFICIENCY ENDPOINT")
print("-" * 80)
response = requests.post(f"{BASE_URL}/efficiency/calculate", json={
    'baseline_production': baseline['value'],
    'current_conditions': {'Vibration': 2.5, 'CondenserVacuum': -700},
    'parameters': {}
})
print(f"Status: {response.status_code}")
if response.status_code == 200:
    efficiency = response.json()
    print(f"✓ Fields: {list(efficiency.keys())}")
    print(f"  adjusted_expected: {efficiency.get('adjusted_expected')}")
    print(f"  total_loss_factor: {efficiency.get('total_loss_factor')}")
    print(f"  loss_breakdown: {efficiency.get('loss_breakdown')}")
    assert 'adjusted_expected' in efficiency, "Missing 'adjusted_expected'"
    assert 'total_loss_factor' in efficiency, "Missing 'total_loss_factor'"
    assert 'loss_breakdown' in efficiency, "Missing 'loss_breakdown'"
else:
    print(f"❌ Error: {response.text}")
    exit(1)

print("\n3️⃣  DELTA ENDPOINT")
print("-" * 80)
response = requests.post(f"{BASE_URL}/delta/calculate", json={
    'actual': 106.5,
    'expected': efficiency['adjusted_expected'],
    'metadata': {'period': 'aggregate'},
    'timestamp': '2025-11-20T12:00:00'
})
print(f"Status: {response.status_code}")
if response.status_code == 200:
    delta = response.json()
    print(f"✓ Fields: {list(delta.keys())}")
    print(f"  weighted_delta: {delta.get('weighted_delta')}")
    print(f"  performance_score: {delta.get('performance_score')}")
    print(f"  condition: {delta.get('condition')}")
    assert 'weighted_delta' in delta, "Missing 'weighted_delta'"
    assert 'performance_score' in delta, "Missing 'performance_score'"
    assert 'condition' in delta, "Missing 'condition'"
else:
    print(f"❌ Error: {response.text}")
    exit(1)

print("\n4️⃣  AVAILABILITY ENDPOINT")
print("-" * 80)
response = requests.post(f"{BASE_URL}/availability/calculate", json={
    'data': sample_data,
    'rated_capacity': 250,
    'time_range': {'start': '2025-11-20T10:00:00', 'end': '2025-11-20T13:00:00'}
})
print(f"Status: {response.status_code}")
if response.status_code == 200:
    availability = response.json()
    print(f"✓ Fields: {list(availability.keys())}")
    print(f"  cumulative_production: {availability.get('cumulative_production')}")
    print(f"  utilization_factor: {availability.get('utilization_factor')}")
    print(f"  total_seconds: {availability.get('total_seconds')}")
    print(f"  availability: {availability.get('availability')}")
    assert 'cumulative_production' in availability, "Missing 'cumulative_production'"
    assert 'utilization_factor' in availability, "Missing 'utilization_factor'"
    assert 'total_seconds' in availability, "Missing 'total_seconds'"
else:
    print(f"❌ Error: {response.text}")
    exit(1)

print("\n5️⃣  INFLUENCE ENDPOINT")
print("-" * 80)
response = requests.post(f"{BASE_URL}/influence/calculate", json={
    'primary_tag': 'TURBINE_LOADMW',
    'influencing_tags': ['TOTAL_COAL_FLOW'],
    'data': sample_data
})
print(f"Status: {response.status_code}")
if response.status_code == 200:
    influence = response.json()
    print(f"✓ Fields: {list(influence.keys())}")
    for tag, corr in influence.items():
        print(f"  {tag}:")
        print(f"    impact_percentage: {corr.get('impact_percentage')}")
        print(f"    lag_minutes: {corr.get('lag_minutes')}")
        print(f"    pearson: {corr.get('pearson')}")
        assert 'impact_percentage' in corr, f"Missing 'impact_percentage' for {tag}"
        assert 'lag_minutes' in corr, f"Missing 'lag_minutes' for {tag}"
        assert 'pearson' in corr, f"Missing 'pearson' for {tag}"
else:
    print(f"❌ Error: {response.text}")
    exit(1)

print("\n6️⃣  STABILITY ENDPOINT")
print("-" * 80)
response = requests.post(f"{BASE_URL}/stability/calculate", json={
    'values': [105.5, 108.2, 106.8, 107.3]
})
print(f"Status: {response.status_code}")
if response.status_code == 200:
    stability = response.json()
    print(f"✓ Fields: {list(stability.keys())}")
    print(f"  index: {stability.get('index')}")
    print(f"  rating: {stability.get('rating')}")
    print(f"  std_dev: {stability.get('std_dev')}")
    print(f"  coefficient_of_variation: {stability.get('coefficient_of_variation')}")
    assert 'std_dev' in stability, "Missing 'std_dev'"
    assert 'coefficient_of_variation' in stability, "Missing 'coefficient_of_variation'"
else:
    print(f"❌ Error: {response.text}")
    exit(1)

print("\n7️⃣  CONDITION ENDPOINT")
print("-" * 80)
response = requests.post(f"{BASE_URL}/condition/score", json={
    'parameter': 'TURBINE_LOADMW',
    'value': 106.5,
    'custom_thresholds': None
})
print(f"Status: {response.status_code}")
if response.status_code == 200:
    condition = response.json()
    print(f"✓ Fields: {list(condition.keys())}")
    print(f"  score: {condition.get('score')}")
    print(f"  status: {condition.get('status')}")
    print(f"  color: {condition.get('color')}")
    assert 'score' in condition, "Missing 'score'"
    assert 'status' in condition, "Missing 'status'"
    assert 'color' in condition, "Missing 'color'"
else:
    print(f"❌ Error: {response.text}")
    exit(1)

print("\n8️⃣  LOSS ATTRIBUTION ENDPOINT")
print("-" * 80)
response = requests.post(f"{BASE_URL}/loss/attribute", json={
    'actual_production': availability['cumulative_production'],
    'expected_production': efficiency['adjusted_expected'] * (availability['total_seconds'] / 3600),
    'influence_map': {
        'TOTAL_COAL_FLOW': {
            'pearson': influence['TOTAL_COAL_FLOW']['pearson'],
            'impact_percentage': influence['TOTAL_COAL_FLOW']['impact_percentage']
        }
    },
    'current_conditions': {'TOTAL_COAL_FLOW': 121.3}
})
print(f"Status: {response.status_code}")
if response.status_code == 200:
    loss = response.json()
    print(f"✓ Fields: {list(loss.keys())}")
    print(f"  total_loss: {loss.get('total_loss')}")
    print(f"  attributed_loss: {loss.get('attributed_loss')}")
    if loss.get('attribution'):
        for param, data in loss['attribution'].items():
            print(f"  {param}:")
            print(f"    loss_amount: {data.get('loss_amount')}")
            print(f"    loss_percentage: {data.get('loss_percentage')}")
            assert 'loss_amount' in data, f"Missing 'loss_amount' for {param}"
            assert 'loss_percentage' in data, f"Missing 'loss_percentage' for {param}"
    assert 'total_loss' in loss, "Missing 'total_loss'"
    assert 'attribution' in loss, "Missing 'attribution'"
else:
    print(f"❌ Error: {response.text}")
    exit(1)

print("\n" + "="*80)
print("✅ ALL 8 ENDPOINTS PASSED")
print("="*80)
print("\nField Naming Verification:")
print("  ✓ baseline: value, std_dev, sample_size, valid_until")
print("  ✓ efficiency: adjusted_expected, total_loss_factor, loss_breakdown")
print("  ✓ delta: weighted_delta, performance_score, condition")
print("  ✓ availability: cumulative_production, utilization_factor, total_seconds")
print("  ✓ influence: impact_percentage, lag_minutes, pearson")
print("  ✓ stability: std_dev, coefficient_of_variation")
print("  ✓ condition: score, status, color")
print("  ✓ loss: total_loss, loss_amount, loss_percentage")
print("\n" + "="*80)
print("READY FOR BROWSER TESTING")
print("="*80 + "\n")
