import requests
import json
from datetime import datetime

# Configuration
API_URL = "http://localhost:7001"

def check_tags():
    """Check all tags being served by the API"""
    print("=" * 80)
    print(f"🔍 Checking All 41 PLC Tags - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    
    try:
        # Get tags list
        tags_response = requests.get(f"{API_URL}/api/tags", timeout=5)
        tags_data = tags_response.json()
        
        print(f"\n📋 Total tags returned: {len(tags_data)}")
        print(f"Expected: 41 PLC tags (server_progid='Rockwel_PLC_001')")
        
        # Get current values
        values_response = requests.get(f"{API_URL}/api/values", timeout=5)
        values_data = values_response.json()
        
        print(f"\n📊 Total values returned: {len(values_data)}")
        
        # Check each tag
        print("\n" + "=" * 80)
        print("TAG DETAILS:")
        print("=" * 80)
        
        numeric_count = 0
        string_count = 0
        missing_values = []
        
        for idx, tag in enumerate(tags_data, 1):
            tag_id = tag['tag_id']
            tag_name = tag.get('tag_name', 'N/A')
            data_type = tag.get('data_type', 'unknown')
            
            # Check if value exists
            if tag_id in values_data:
                value_info = values_data[tag_id]
                value = value_info.get('value', 'N/A')
                timestamp = value_info.get('timestamp', 'N/A')
                
                # Count types
                if data_type in ['REAL', 'DINT', 'INT']:
                    numeric_count += 1
                    display_value = f"{value:.2f}" if isinstance(value, (int, float)) else str(value)
                else:
                    string_count += 1
                    display_value = str(value) if value is not None else "---"
                
                print(f"{idx:2d}. ✅ {tag_id:40s} | Type: {data_type:6s} | Value: {display_value}")
            else:
                missing_values.append(tag_id)
                print(f"{idx:2d}. ❌ {tag_id:40s} | Type: {data_type:6s} | Value: MISSING")
        
        # Summary
        print("\n" + "=" * 80)
        print("SUMMARY:")
        print("=" * 80)
        print(f"✅ Total tags in API:        {len(tags_data)}")
        print(f"✅ Tags with values:         {len(values_data)}")
        print(f"✅ Numeric tags (REAL/DINT): {numeric_count}")
        print(f"✅ String tags:              {string_count}")
        
        if missing_values:
            print(f"\n❌ Tags without values ({len(missing_values)}):")
            for tag_id in missing_values:
                print(f"   - {tag_id}")
        else:
            print(f"\n✅ ALL {len(tags_data)} TAGS HAVE VALUES!")
        
        # Check specific welding parameters
        print("\n" + "=" * 80)
        print("WELDING PARAMETERS STATUS:")
        print("=" * 80)
        
        welding_tags = [
            'Welding_Current_A',
            'Welding_Voltage_V',
            'Pipe_Id',
            'WPS_ID',
            'Joint_Id',
            'Arc'
        ]
        
        for tag_id in welding_tags:
            if tag_id in values_data:
                value = values_data[tag_id].get('value')
                if value is None or value == '' or value == 0:
                    print(f"⚠️  {tag_id:25s} = {value} (may show as '---' in UI)")
                else:
                    print(f"✅ {tag_id:25s} = {value}")
            else:
                print(f"❌ {tag_id:25s} = NOT FOUND IN API")
        
        print("\n" + "=" * 80)
        
    except requests.exceptions.ConnectionError:
        print("\n❌ ERROR: Cannot connect to server at http://localhost:7001")
        print("   Make sure plc_scanner_web.py is running!")
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    check_tags()
