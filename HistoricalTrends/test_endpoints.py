#!/usr/bin/env python3
"""
Quick endpoint validation script
Tests availability & influence endpoints with minimal payload
"""
import requests
import json
from datetime import datetime, timedelta

BASE_URL = 'http://127.0.0.1:5002/api/v1'

def test_availability():
    """Test availability endpoint"""
    print("=" * 60)
    print("Testing /api/v1/availability/calculate")
    print("=" * 60)
    
    data = []
    start_time = datetime.now()
    for i in range(12):
        data.append({
            'Timestamp': (start_time + timedelta(minutes=i)).isoformat(),
            'TURBINE_LOADMW': 100 + (i * 2),
            'TOTAL_COAL_FLOW': 200 + (i * 3)
        })
    
    payload = {
        'data': data,
        'rated_capacity': 270,
        'load_col': 'TURBINE_LOADMW'
    }
    
    try:
        response = requests.post(f'{BASE_URL}/availability/calculate', json=payload)
        print(f"Status: {response.status_code}")
        result = response.json()
        print(json.dumps(result, indent=2))
        
        if response.status_code == 200:
            print("\n✓ AVAILABILITY: PASS")
            return True
        else:
            print(f"\n❌ AVAILABILITY: FAIL - {result.get('error')}")
            return False
    except Exception as e:
        print(f"❌ Exception: {e}")
        return False

def test_influence():
    """Test influence endpoint"""
    print("\n" + "=" * 60)
    print("Testing /api/v1/influence/calculate")
    print("=" * 60)
    
    data = []
    start_time = datetime.now()
    for i in range(20):
        data.append({
            'Timestamp': (start_time + timedelta(minutes=i)).isoformat(),
            'TURBINE_LOADMW': 100 + (i * 2),
            'TOTAL_COAL_FLOW': 200 + (i * 3),
            'BEARING_VIB_HP_FRONT-XMICRO_METER-UM': 20 + (i * 0.5)
        })
    
    payload = {
        'data': data,
        'primary_tag': 'TURBINE_LOADMW',
        'influencing_tags': ['TOTAL_COAL_FLOW', 'BEARING_VIB_HP_FRONT-XMICRO_METER-UM']
    }
    
    try:
        response = requests.post(f'{BASE_URL}/influence/calculate', json=payload)
        print(f"Status: {response.status_code}")
        result = response.json()
        print(json.dumps(result, indent=2))
        
        if response.status_code == 200:
            print("\n✓ INFLUENCE: PASS")
            return True
        else:
            print(f"\n❌ INFLUENCE: FAIL - {result.get('error')}")
            return False
    except Exception as e:
        print(f"❌ Exception: {e}")
        return False

def test_baseline():
    """Test baseline endpoint"""
    print("\n" + "=" * 60)
    print("Testing /api/v1/baseline/calculate")
    print("=" * 60)
    
    data = []
    start_time = datetime.now()
    for i in range(100):
        data.append({
            'Timestamp': (start_time + timedelta(minutes=i)).isoformat(),
            'TURBINE_LOADMW': 240 + (i % 30) - 15
        })
    
    payload = {
        'data': data,
        'tag': 'TURBINE_LOADMW'
    }
    
    try:
        response = requests.post(f'{BASE_URL}/baseline/calculate', json=payload)
        print(f"Status: {response.status_code}")
        result = response.json()
        print(json.dumps(result, indent=2))
        
        if response.status_code == 200:
            print("\n✓ BASELINE: PASS")
            return True
        else:
            print(f"\n❌ BASELINE: FAIL")
            return False
    except Exception as e:
        print(f"❌ Exception: {e}")
        return False

if __name__ == '__main__':
    print("\n" + "=" * 60)
    print("ADVANCED BI ENDPOINT VALIDATION")
    print("=" * 60 + "\n")
    
    results = {}
    results['availability'] = test_availability()
    results['influence'] = test_influence()
    results['baseline'] = test_baseline()
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for endpoint, passed in results.items():
        status = "✓ PASS" if passed else "❌ FAIL"
        print(f"{endpoint.upper()}: {status}")
    
    all_passed = all(results.values())
    print("=" * 60)
    if all_passed:
        print("✓ ALL TESTS PASSED")
    else:
        print("❌ SOME TESTS FAILED")
    print("=" * 60 + "\n")
