import requests
import json

# Check API for all tags
try:
    response = requests.get('http://localhost:5001/api/opc/values', timeout=5)
    if response.status_code == 200:
        data = response.json()
        
        print("\n" + "="*80)
        print("CHECKING TAG VALUES POOL API")
        print("="*80)
        
        welding_tags = [
            'Welding_Current_A', 'Welding_Voltage_V', 'Arc', 'Power', 
            'Pipe_Id', 'Joint_Id', 'Welder_id', 'WPS_ID', 'sim_step'
        ]
        
        print(f"\nTotal tags in API: {len(data['tags'])}")
        print(f"\nWelding tags status:")
        print("-" * 80)
        
        found_tags = []
        for tag in data['tags']:
            if tag['tagId'] in welding_tags:
                found_tags.append(tag['tagId'])
                print(f"✅ {tag['tagId']:25s} = {str(tag['value']):15s} | Quality: {tag['quality']}")
        
        print("\nMissing welding tags:")
        print("-" * 80)
        missing = set(welding_tags) - set(found_tags)
        for tag_id in sorted(missing):
            print(f"❌ {tag_id:25s} - NOT IN API")
        
        print("\n" + "="*80)
        print(f"Summary: {len(found_tags)}/{len(welding_tags)} welding tags available")
        print("="*80)
        
    else:
        print(f"❌ API returned status {response.status_code}")
        
except Exception as e:
    print(f"❌ Error connecting to API: {e}")
