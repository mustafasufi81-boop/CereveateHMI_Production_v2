"""
Quick test to verify /api/config returns GroupedBarSettings
"""
import requests
import json

try:
    response = requests.get('http://127.0.0.1:5002/api/config', timeout=5)
    if response.status_code == 200:
        config = response.json()
        
        print("="*80)
        print("CONFIG API VERIFICATION")
        print("="*80)
        
        if 'GroupedBarSettings' in config:
            print("\n✅ GroupedBarSettings found in config!")
            print(f"\nGroupedBarSettings:")
            for key, value in config['GroupedBarSettings'].items():
                print(f"   {key}: {value}")
        else:
            print("\n❌ GroupedBarSettings NOT found in config!")
            print(f"\nAvailable keys: {list(config.keys())}")
            
        print("\n" + "="*80)
    else:
        print(f"❌ API returned status {response.status_code}")
        
except Exception as e:
    print(f"❌ Error: {e}")
