#!/usr/bin/env python3
"""
Test condition/score and loss/attribute endpoints with None/missing values
"""
import requests
import json

BASE_URL = 'http://127.0.0.1:5002/api/v1'

def test_condition_score_with_none():
    """Test condition score with None value"""
    print("=" * 60)
    print("Testing /api/v1/condition/score with None value")
    print("=" * 60)
    
    payload = {
        'parameter': 'Vibration',
        'value': None  # This was causing the error
    }
    
    try:
        response = requests.post(f'{BASE_URL}/condition/score', json=payload)
        print(f"Status: {response.status_code}")
        result = response.json()
        print(json.dumps(result, indent=2))
        
        if response.status_code == 200:
            print("\n✓ CONDITION SCORE (None value): PASS")
            return True
        else:
            print(f"\n❌ CONDITION SCORE (None value): FAIL - {result.get('error')}")
            return False
    except Exception as e:
        print(f"❌ Exception: {e}")
        return False

def test_condition_score_with_valid():
    """Test condition score with valid value"""
    print("\n" + "=" * 60)
    print("Testing /api/v1/condition/score with valid value")
    print("=" * 60)
    
    payload = {
        'parameter': 'Vibration',
        'value': 2.5
    }
    
    try:
        response = requests.post(f'{BASE_URL}/condition/score', json=payload)
        print(f"Status: {response.status_code}")
        result = response.json()
        print(json.dumps(result, indent=2))
        
        if response.status_code == 200:
            print("\n✓ CONDITION SCORE (valid value): PASS")
            return True
        else:
            print(f"\n❌ CONDITION SCORE (valid value): FAIL")
            return False
    except Exception as e:
        print(f"❌ Exception: {e}")
        return False

def test_loss_attribution_missing_keys():
    """Test loss attribution with missing keys"""
    print("\n" + "=" * 60)
    print("Testing /api/v1/loss/attribute with missing keys")
    print("=" * 60)
    
    # Missing 'actual_production', using 'actual' instead
    payload = {
        'actual': 200,
        'expected': 250,
        'influence_map': {
            'Vibration': {
                'pearson': 0.8,
                'impact_percentage': 5.0,
                'is_significant': True
            }
        },
        'current_conditions': {
            'Vibration': 4.5
        }
    }
    
    try:
        response = requests.post(f'{BASE_URL}/loss/attribute', json=payload)
        print(f"Status: {response.status_code}")
        result = response.json()
        print(json.dumps(result, indent=2))
        
        if response.status_code == 200:
            print("\n✓ LOSS ATTRIBUTION (alternate keys): PASS")
            return True
        else:
            print(f"\n❌ LOSS ATTRIBUTION (alternate keys): FAIL - {result.get('error')}")
            return False
    except Exception as e:
        print(f"❌ Exception: {e}")
        return False

def test_loss_attribution_standard():
    """Test loss attribution with standard keys"""
    print("\n" + "=" * 60)
    print("Testing /api/v1/loss/attribute with standard keys")
    print("=" * 60)
    
    payload = {
        'actual_production': 200,
        'expected_production': 250,
        'influence_map': {
            'Vibration': {
                'pearson': 0.8,
                'impact_percentage': 5.0,
                'is_significant': True
            },
            'NOx': {
                'pearson': 0.6,
                'impact_percentage': 3.0,
                'is_significant': True
            }
        },
        'current_conditions': {
            'Vibration': 4.5,
            'NOx': 180
        }
    }
    
    try:
        response = requests.post(f'{BASE_URL}/loss/attribute', json=payload)
        print(f"Status: {response.status_code}")
        result = response.json()
        print(json.dumps(result, indent=2))
        
        if response.status_code == 200:
            print("\n✓ LOSS ATTRIBUTION (standard keys): PASS")
            return True
        else:
            print(f"\n❌ LOSS ATTRIBUTION (standard keys): FAIL")
            return False
    except Exception as e:
        print(f"❌ Exception: {e}")
        return False

if __name__ == '__main__':
    print("\n" + "=" * 60)
    print("CONDITION SCORE & LOSS ATTRIBUTION ERROR HANDLING TESTS")
    print("=" * 60 + "\n")
    
    results = {}
    results['condition_none'] = test_condition_score_with_none()
    results['condition_valid'] = test_condition_score_with_valid()
    results['loss_alternate_keys'] = test_loss_attribution_missing_keys()
    results['loss_standard_keys'] = test_loss_attribution_standard()
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for test_name, passed in results.items():
        status = "✓ PASS" if passed else "❌ FAIL"
        print(f"{test_name.upper()}: {status}")
    
    all_passed = all(results.values())
    print("=" * 60)
    if all_passed:
        print("✓ ALL TESTS PASSED")
    else:
        print("❌ SOME TESTS FAILED")
    print("=" * 60 + "\n")
