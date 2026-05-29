#!/usr/bin/env python3
"""
Test if configuration values are being read correctly
"""

import requests
import json

print("=" * 70)
print("CONFIGURATION TEST - Reading DesignFactor")
print("=" * 70)

# Test 1: Read config from API
print("\n1️⃣  Reading configuration from /api/config...")
try:
    response = requests.get('http://127.0.0.1:5002/api/config')
    config = response.json()
    
    print("✓ Config loaded successfully")
    print(f"\n📋 Full config structure:")
    print(json.dumps(config, indent=2))
    
    # Check if our settings exist
    print(f"\n2️⃣  Checking GroupedBarSettings:")
    if 'GroupedBarSettings' in config:
        gbs = config['GroupedBarSettings']
        print(f"   ✓ GroupedBarSettings found")
        print(f"   DesignFactor: {gbs.get('DesignFactor', 'NOT FOUND')}")
        print(f"   LastPeriodPercentile: {gbs.get('LastPeriodPercentile', 'NOT FOUND')}")
        print(f"   EnableAutoDetection: {gbs.get('EnableAutoDetection', 'NOT FOUND')}")
        
        # Verify it's 1.50
        if gbs.get('DesignFactor') == 1.50:
            print(f"\n   ✅ SUCCESS! DesignFactor is 1.50 (50% margin)")
        else:
            print(f"\n   ❌ FAIL! Expected 1.50, got {gbs.get('DesignFactor')}")
    else:
        print("   ❌ GroupedBarSettings NOT FOUND in config")
    
    print(f"\n3️⃣  Checking TimeSeriesBarSettings:")
    if 'TimeSeriesBarSettings' in config:
        tsbs = config['TimeSeriesBarSettings']
        print(f"   ✓ TimeSeriesBarSettings found")
        print(f"   DesignFactor: {tsbs.get('DesignFactor', 'NOT FOUND')}")
        print(f"   AutoTimeGrouping: {tsbs.get('AutoTimeGrouping', 'NOT FOUND')}")
        
        # Verify it's 1.50
        if tsbs.get('DesignFactor') == 1.50:
            print(f"\n   ✅ SUCCESS! DesignFactor is 1.50 (50% margin)")
        else:
            print(f"\n   ❌ FAIL! Expected 1.50, got {tsbs.get('DesignFactor')}")
    else:
        print("   ❌ TimeSeriesBarSettings NOT FOUND in config")
    
except Exception as e:
    print(f"❌ Error: {e}")

print("\n" + "=" * 70)
print("TEST COMPLETE")
print("=" * 70)
print("\n💡 EXPECTED RESULT:")
print("   - DesignFactor should be 1.50 (50% margin)")
print("   - LastPeriodPercentile should be 0.90 (90th percentile)")
print("\n💡 VISUAL TEST:")
print("   1. Refresh browser (Ctrl+Shift+R)")
print("   2. Load data and select tags")
print("   3. Click Grouped Bar")
print("   4. Check console for: 'Using: DesignFactor=1.5'")
print("   5. Blue bars (Design) should be 50% taller than green bars (Current)")
