"""
Direct test of efficiency endpoint to see actual response
"""
import requests
import json

BASE_URL = "http://127.0.0.1:5002/api/v1"

print("\n" + "="*80)
print("TESTING EFFICIENCY ENDPOINT DIRECTLY")
print("="*80)

# Test 1: Call efficiency with baseline value
print("\n📊 TEST 1: Efficiency with baseline_value=105.58")
print("-" * 80)

payload = {
    'baseline_production': 105.58,
    'current_conditions': {},
    'parameters': {}
}

print(f"Sending: {json.dumps(payload, indent=2)}")

try:
    response = requests.post(f"{BASE_URL}/efficiency/calculate", json=payload, timeout=5)
    print(f"\nStatus: {response.status_code}")
    
    if response.status_code == 200:
        result = response.json()
        print(f"\n✓ Response:")
        print(json.dumps(result, indent=2))
        
        print(f"\n🔍 Field Analysis:")
        print(f"  baseline: {result.get('baseline')} (type: {type(result.get('baseline'))})")
        print(f"  adjusted_expected: {result.get('adjusted_expected')} (type: {type(result.get('adjusted_expected'))})")
        print(f"  total_loss_factor: {result.get('total_loss_factor')} (type: {type(result.get('total_loss_factor'))})")
        print(f"  loss_breakdown: {result.get('loss_breakdown')}")
        
        # Check if adjusted_expected is 0
        if result.get('adjusted_expected') == 0:
            print(f"\n⚠️  WARNING: adjusted_expected is 0!")
            print(f"  This means: baseline * (1 - total_loss_factor) = {result.get('baseline')} * (1 - {result.get('total_loss_factor')})")
            
    else:
        print(f"❌ Error: {response.text}")
        
except Exception as e:
    print(f"❌ Exception: {e}")
    import traceback
    traceback.print_exc()

# Test 2: Call with some conditions
print("\n\n📊 TEST 2: Efficiency with conditions")
print("-" * 80)

payload2 = {
    'baseline_production': 105.58,
    'current_conditions': {'Vibration': 2.5, 'CondenserVacuum': -700},
    'parameters': {}
}

print(f"Sending: {json.dumps(payload2, indent=2)}")

try:
    response = requests.post(f"{BASE_URL}/efficiency/calculate", json=payload2, timeout=5)
    print(f"\nStatus: {response.status_code}")
    
    if response.status_code == 200:
        result = response.json()
        print(f"\n✓ Response:")
        print(json.dumps(result, indent=2))
        
except Exception as e:
    print(f"❌ Exception: {e}")

print("\n" + "="*80)
print("TEST COMPLETE")
print("="*80 + "\n")
