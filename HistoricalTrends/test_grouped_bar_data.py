"""
Test script to verify Grouped Bar data structure and numeric field detection
This script simulates what the JavaScript receives and tests the auto-detection logic
"""

import requests
import json
from datetime import datetime, timedelta

def test_grouped_bar_api():
    """Test the data returned from the Flask API"""
    
    base_url = "http://127.0.0.1:5002"
    
    print("=" * 80)
    print("GROUPED BAR DATA STRUCTURE TEST")
    print("=" * 80)
    
    # Step 1: Get available tags
    print("\n1️⃣  Fetching available tags...")
    try:
        response = requests.get(f"{base_url}/api/tags", timeout=5)
        if response.status_code == 200:
            tags_data = response.json()
            print(f"✅ Tags API Response: {tags_data}")
            
            if 'tags' in tags_data:
                available_tags = tags_data['tags']
                print(f"✅ Available tags ({len(available_tags)}): {available_tags[:10]}")  # Show first 10
            else:
                print("❌ No 'tags' key in response")
                return
        else:
            print(f"❌ Tags API failed: {response.status_code}")
            return
    except Exception as e:
        print(f"❌ Error fetching tags: {e}")
        return
    
    # Step 2: Get sample data for a tag
    print("\n2️⃣  Fetching sample data for first 5 tags...")
    # Use date range with actual data (Jan-Mar 2025)
    start_date = datetime(2025, 3, 1)
    end_date = datetime(2025, 3, 20)
    
    # Use first 5 tags for testing
    test_tags = available_tags[:5] if len(available_tags) >= 5 else available_tags
    
    params = {
        'tags': ','.join(test_tags),
        'start_date': start_date.strftime('%Y-%m-%d'),
        'end_date': end_date.strftime('%Y-%m-%d')
    }
    
    try:
        response = requests.get(f"{base_url}/api/data", params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Data API Response status: SUCCESS")
            print(f"✅ Response has 'data' key: {'data' in data}")
            
            if 'data' in data and len(data['data']) > 0:
                sample_data = data['data']
                print(f"✅ Data points returned: {len(sample_data)}")
                
                # Analyze first row
                first_row = sample_data[0]
                print(f"\n3️⃣  First row structure:")
                print(f"   Keys: {list(first_row.keys())}")
                print(f"   Sample row: {first_row}")
                
                # Check data types (simulating JavaScript auto-detection)
                print(f"\n4️⃣  Field type analysis (simulating JavaScript):")
                numeric_tags = []
                
                for key in first_row.keys():
                    value = first_row[key]
                    lower_key = key.lower()
                    
                    # Replicate JavaScript logic
                    is_timestamp = lower_key == 'timestamp'
                    is_number = isinstance(value, (int, float))
                    is_valid = not is_timestamp and is_number and not (value != value)  # NaN check
                    
                    symbol = "✅" if is_valid else "❌"
                    print(f"   {symbol} {key}: type={type(value).__name__}, value={value}, valid_numeric={is_valid}")
                    
                    if is_valid:
                        numeric_tags.append(key)
                
                print(f"\n5️⃣  Auto-detected numeric tags: {numeric_tags}")
                print(f"   Count: {len(numeric_tags)}")
                
                if len(numeric_tags) == 0:
                    print("\n❌ PROBLEM IDENTIFIED: No numeric tags detected!")
                    print("   This explains the 'No numeric tags found!' error")
                    
                    # Debug: Check what Python sees vs what JavaScript would see
                    print("\n🔍 Debugging - Python vs JavaScript type conversion:")
                    for key, value in first_row.items():
                        print(f"   {key}:")
                        print(f"      Python type: {type(value)}")
                        print(f"      Python isinstance(value, (int, float)): {isinstance(value, (int, float))}")
                        print(f"      JSON serializes to: {json.dumps(value)}")
                else:
                    print(f"\n✅ SUCCESS: Found {len(numeric_tags)} numeric tags")
                    print(f"   First 6 tags for Grouped Bar: {numeric_tags[:6]}")
                    
                    # Calculate statistics for each tag
                    print(f"\n6️⃣  Statistics calculation test:")
                    for tag in numeric_tags[:3]:  # Test first 3 tags
                        values = [row[tag] for row in sample_data if tag in row and isinstance(row[tag], (int, float))]
                        
                        if len(values) > 0:
                            sorted_values = sorted(values)
                            design = sorted_values[-1] * 1.05
                            last_period = values[int(len(values) * 0.75)]
                            current = values[-1]
                            
                            print(f"   {tag}:")
                            print(f"      Design (max * 1.05): {design:.2f}")
                            print(f"      Last Period (75%): {last_period:.2f}")
                            print(f"      Current (latest): {current:.2f}")
                
            else:
                print("❌ No data returned or empty data array")
                print(f"   Response keys: {data.keys()}")
                
        else:
            print(f"❌ Data API failed: {response.status_code}")
            print(f"   Response: {response.text}")
            
    except Exception as e:
        print(f"❌ Error fetching data: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)

if __name__ == "__main__":
    test_grouped_bar_api()
