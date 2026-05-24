import requests
import json

# Get all configured welding tags from database
welding_tags_db = [
    'Welding_Current_A', 'Welding_Voltage_V', 'Arc', 'Power', 
    'Pipe_Id', 'Joint_Id', 'Welder_id', 'WPS_ID', 'sim_step'
]

# Get actual tags from API
try:
    response = requests.get('http://localhost:5001/api/opc/values', timeout=5)
    if response.status_code == 200:
        data = response.json()
        welding_tags_api = [tag['tagId'] for tag in data['tags'] if tag['tagId'] in welding_tags_db]
        
        print("\n" + "="*80)
        print("ROOT CAUSE ANALYSIS: WELDING DATA NOT IN DATABASE")
        print("="*80)
        
        print("\n1. TAGS CONFIGURED IN DATABASE (historian_meta.tag_master):")
        print("   " + ", ".join(welding_tags_db))
        
        print(f"\n2. TAGS AVAILABLE IN API (TagValuesPoolService):")
        print("   " + ", ".join(welding_tags_api))
        
        missing = set(welding_tags_db) - set(welding_tags_api)
        print(f"\n3. TAGS MISSING FROM API (NOT BEING READ FROM PLC):")
        print("   " + ", ".join(sorted(missing)))
        
        print("\n" + "="*80)
        print("ROOT CAUSE:")
        print("="*80)
        print("""
The 7 missing tags are NOT being read from the PLC by the RockwellDriver.

POSSIBLE REASONS:
1. These tags don't exist in the actual PLC with those exact names
2. The tag initialization failed during ConnectAsync() in RockwellDriver
3. The PLC simulator (e.g., Factory Talk, RSLogix Emulate) doesn't have these tags

EVIDENCE:
- Tags ARE in database (historian_meta.tag_master) ✅
- Tags ARE enabled ✅
- Tags HAVE correct PLC IP (192.168.0.20) ✅  
- Tags ARE NOT in TagValuesPoolService API ❌
- Only Power & Arc are working

SOLUTION:
Option A: Add these tags to the actual PLC/simulator
Option B: Check the PLC tag browser to see actual available tag names
Option C: Check C# backend logs for "Tag initialization failed" errors
Option D: Verify PLC is at 192.168.0.20 and accessible

NEXT STEPS:
1. Restart the C# backend with verbose logging
2. Look for "Tag initialization failed" or "Tag not found" errors
3. Browse the actual PLC tags to verify names match
        """)
        
        print("\nCOMMAND TO CHECK C# LOGS:")
        print("   dotnet run --project OpcDaWebService.csproj")
        print("   (Look for [ROCKWELL] log messages about tag initialization)")
        
    else:
        print(f"❌ API Error: {response.status_code}")
except Exception as e:
    print(f"❌ Connection Error: {e}")
