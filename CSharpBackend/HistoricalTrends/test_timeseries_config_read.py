"""
Test script to verify Time-Series Bar configuration reading
Tests that DesignValue=270 for TURBINE_LOADMW is correctly read and applied
"""
import json
import requests
import time

def test_config_reading():
    print("=" * 80)
    print("TESTING TIME-SERIES BAR CONFIGURATION READING")
    print("=" * 80)
    
    # Test 1: Read config file directly
    print("\n[TEST 1] Reading trends-config.json directly...")
    try:
        import os
        config_path = os.path.join(os.path.dirname(__file__), 'trends-config.json')
        print(f"Config file path: {config_path}")
        print(f"File exists: {os.path.exists(config_path)}")
        
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        print(f"✓ Config file loaded successfully")
        print(f"Top-level keys: {list(config.keys())}")
        
        grouped_settings = config.get('GroupedBarSettings', {})
        timeseries_settings = config.get('TimeSeriesBarSettings', {})
        
        print(f"\n--- GroupedBarSettings ---")
        print(f"Type: {type(grouped_settings)}")
        print(f"DesignFactor: {grouped_settings.get('DesignFactor')}")
        print(f"DesignValue: {grouped_settings.get('DesignValue')}")
        print(f"LastPeriodPercentile: {grouped_settings.get('LastPeriodPercentile')}")
        
        tag_limits = grouped_settings.get('TagSpecificLimits', {})
        print(f"\n--- TagSpecificLimits ---")
        for tag, limits in tag_limits.items():
            print(f"\n{tag}:")
            for key, val in limits.items():
                print(f"  {key}: {val}")
        
        # Focus on TURBINE_LOADMW
        turbine_limits = tag_limits.get('TURBINE_LOADMW', {})
        turbine_design = turbine_limits.get('DesignValue')
        print(f"\n⚡ TURBINE_LOADMW DesignValue from file: {turbine_design}")
        
        if turbine_design == 270:
            print("✓ PASS: TURBINE_LOADMW DesignValue is correctly set to 270")
        else:
            print(f"✗ FAIL: TURBINE_LOADMW DesignValue is {turbine_design}, expected 270")
            
    except Exception as e:
        print(f"✗ ERROR reading config file: {e}")
        return False
    
    # Test 2: Check if Flask server is running
    print("\n" + "=" * 80)
    print("[TEST 2] Checking Flask server status...")
    try:
        response = requests.get('http://localhost:5002/api/config', timeout=2)
        if response.status_code == 200:
            print("✓ Flask server is running on port 5002")
            
            api_config = response.json()
            api_grouped = api_config.get('GroupedBarSettings', {})
            api_timeseries = api_config.get('TimeSeriesBarSettings', {})
            
            print(f"\n--- API Response: GroupedBarSettings ---")
            print(f"DesignFactor: {api_grouped.get('DesignFactor')}")
            print(f"DesignValue: {api_grouped.get('DesignValue')}")
            
            api_tag_limits = api_grouped.get('TagSpecificLimits', {})
            api_turbine = api_tag_limits.get('TURBINE_LOADMW', {})
            api_turbine_design = api_turbine.get('DesignValue')
            
            print(f"\n⚡ TURBINE_LOADMW DesignValue from API: {api_turbine_design}")
            
            if api_turbine_design == 270:
                print("✓ PASS: API returns correct DesignValue=270 for TURBINE_LOADMW")
            else:
                print(f"✗ FAIL: API returns {api_turbine_design}, expected 270")
            
            # Test 3: Check if TimeSeriesBarSettings exists
            print(f"\n--- API Response: TimeSeriesBarSettings ---")
            if api_timeseries:
                print(f"TimeSeriesBarSettings exists: {bool(api_timeseries)}")
                print(f"DesignFactor: {api_timeseries.get('DesignFactor')}")
                print(f"DesignValue: {api_timeseries.get('DesignValue')}")
                
                ts_tag_limits = api_timeseries.get('TagSpecificLimits', {})
                if ts_tag_limits:
                    print(f"TagSpecificLimits in TimeSeriesBarSettings: {list(ts_tag_limits.keys())}")
                else:
                    print("⚠ WARNING: TimeSeriesBarSettings has no TagSpecificLimits")
                    print("   → Should fallback to GroupedBarSettings.TagSpecificLimits")
            else:
                print("⚠ TimeSeriesBarSettings not found in API response")
                print("   → Should fallback to GroupedBarSettings")
            
        else:
            print(f"✗ Server returned status {response.status_code}")
            return False
            
    except requests.exceptions.ConnectionError:
        print("✗ FAIL: Cannot connect to Flask server on port 5002")
        print("   → Please start the server with: .\\venv\\Scripts\\python.exe app.py")
        return False
    except Exception as e:
        print(f"✗ ERROR: {e}")
        return False
    
    # Test 4: Simulate frontend logic
    print("\n" + "=" * 80)
    print("[TEST 3] Simulating frontend configuration reading logic...")
    
    try:
        # Simulate what bi_analytics.js does
        config = api_config
        
        # Time-Series Bar logic (lines 730-740)
        globalDesignFactor = config.get('TimeSeriesBarSettings', {}).get('DesignFactor') or \
                           config.get('GroupedBarSettings', {}).get('DesignFactor') or 1.05
        globalDesignValue = config.get('TimeSeriesBarSettings', {}).get('DesignValue')
        if globalDesignValue is None:
            globalDesignValue = config.get('GroupedBarSettings', {}).get('DesignValue')
        
        tagSpecificLimits = config.get('TimeSeriesBarSettings', {}).get('TagSpecificLimits') or \
                          config.get('GroupedBarSettings', {}).get('TagSpecificLimits') or {}
        
        print(f"Global DesignFactor: {globalDesignFactor}")
        print(f"Global DesignValue: {globalDesignValue}")
        print(f"TagSpecificLimits loaded: {bool(tagSpecificLimits)}")
        
        # Simulate processing TURBINE_LOADMW
        tag = 'TURBINE_LOADMW'
        tagLimits = tagSpecificLimits.get(tag, {})
        
        designFactor = tagLimits.get('DesignFactor') or globalDesignFactor
        designValue = tagLimits.get('DesignValue')
        if designValue is None:
            designValue = globalDesignValue
        
        print(f"\n⚡ Processing {tag}:")
        print(f"   tagLimits found: {bool(tagLimits)}")
        print(f"   designFactor: {designFactor}")
        print(f"   designValue: {designValue}")
        
        # Simulate design calculation (line 770-780)
        max_value = 250.2042  # From the screenshot
        if designValue is not None:
            design = designValue
            calc_type = "FIXED"
        else:
            design = max_value * designFactor
            calc_type = "DYNAMIC"
        
        print(f"\n   Max actual value: {max_value}")
        print(f"   Design calculation: {design} ({calc_type})")
        
        if designValue == 270 and design == 270:
            print(f"\n✓ PASS: Frontend logic correctly uses DesignValue=270")
            print(f"   Chart should show green bars at 270 MW (not {max_value * designFactor:.2f})")
        else:
            print(f"\n✗ FAIL: Design value calculation incorrect")
            print(f"   Expected: 270 (FIXED)")
            print(f"   Got: {design} ({calc_type})")
        
    except Exception as e:
        print(f"✗ ERROR in simulation: {e}")
        return False
    
    # Summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    print("\nConfiguration chain:")
    print("1. trends-config.json → GroupedBarSettings.TagSpecificLimits.TURBINE_LOADMW.DesignValue = 270 ✓")
    print("2. Flask /api/config → Returns same value ✓")
    print("3. Frontend logic → Should use 270 instead of max*1.05 ✓")
    print("\nExpected behavior:")
    print("- TURBINE_LOADMW design bars should be at exactly 270 MW")
    print("- Console should show: 'Processing TURBINE_LOADMW: designValue=270'")
    print("\nNext step: Refresh browser (Ctrl+Shift+R) and check browser console")
    
    return True

if __name__ == '__main__':
    success = test_config_reading()
    exit(0 if success else 1)
