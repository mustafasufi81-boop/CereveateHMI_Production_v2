import requests
import json

print("\n" + "="*80)
print("CHECKING PLC GATEWAY API - HOW MANY TAGS ARE ACTUALLY LOADED")
print("="*80)

# Check if service is running
try:
    # Try to get all values
    response = requests.get('http://localhost:5001/api/plc-gateway/values', timeout=3)
    
    if response.status_code == 200:
        data = response.json()
        total_count = data.get('count', 0)
        values = data.get('values', [])
        
        print(f"\n✅ PLC Gateway API is running")
        print(f"Total tags: {total_count}")
        
        # Check for welding tags
        welding_tags = [v for v in values if any(x in v.get('tagId', '') for x in 
                       ['Welding', 'Arc', 'Power', 'Pipe_Id', 'Joint_Id', 'Welder', 'WPS_ID', 'sim_step'])]
        
        print(f"\nWelding tags found: {len(welding_tags)}/9")
        for tag in welding_tags:
            print(f"   ✅ {tag['tagId']:25s} | Value: {tag.get('value', 'N/A')}")
        
        if len(welding_tags) < 9:
            print(f"\n❌ MISSING {9 - len(welding_tags)} welding tags!")
            missing_ids = ['Welding_Current_A', 'Welding_Voltage_V', 'Arc', 'Power', 
                          'Pipe_Id', 'Joint_Id', 'Welder_id', 'WPS_ID', 'sim_step']
            found_ids = [t['tagId'] for t in welding_tags]
            for mid in missing_ids:
                if mid not in found_ids:
                    print(f"   - {mid}")
    
    # Try specific PLC endpoint
    print("\n" + "-"*80)
    response2 = requests.get('http://localhost:5001/api/plc-gateway/values/Rockwel_PLC_001', timeout=3)
    
    if response2.status_code == 200:
        data2 = response2.json()
        plc_count = data2.get('count', 0)
        plc_values = data2.get('values', [])
        
        print(f"\n✅ Rockwel_PLC_001 specific endpoint")
        print(f"Tags from this PLC: {plc_count}")
        
        welding_in_plc = [v for v in plc_values if any(x in v.get('tagId', '') for x in 
                         ['Welding', 'Arc', 'Power', 'Pipe_Id', 'Joint_Id', 'Welder', 'WPS_ID', 'sim_step'])]
        print(f"Welding tags in this PLC: {len(welding_in_plc)}/9")
        
        if len(welding_in_plc) < 9:
            print("\n⚠️  Welding tags are NOT being loaded by PlcConfigLoaderService!")
            print("    Reason: Service needs restart to reload from database")
    
    # Try status endpoint
    print("\n" + "-"*80)
    response3 = requests.get('http://localhost:5001/api/plc-gateway/status', timeout=3)
    
    if response3.status_code == 200:
        data3 = response3.json()
        plcs = data3.get('connections', [])
        
        print(f"\n✅ Status endpoint")
        print(f"Connected PLCs: {len(plcs)}")
        
        for plc in plcs:
            print(f"\n   PLC: {plc.get('plcId')}")
            print(f"   Protocol: {plc.get('protocol')}")
            print(f"   IP: {plc.get('ipAddress')}:{plc.get('port')}")
            print(f"   Connected: {plc.get('isConnected')}")
            print(f"   Tags: {plc.get('tagCount')}")  # THIS IS THE KEY NUMBER!
            print(f"   Pool Tags: {plc.get('poolTagCount')}")

except requests.exceptions.ConnectionError:
    print("\n❌ PLC Gateway service is NOT RUNNING on port 5001")
    print("\nTO START:")
    print("   cd D:\\Development\\MQTT_Implemented_OPC\\BACKUP_BEFORE_HISTORICAL_20251117_225747 - Copy_backup_20251206")
    print("   dotnet run --project OpcDaWebService.csproj")

except Exception as e:
    print(f"\n❌ Error: {e}")

print("\n" + "="*80)
