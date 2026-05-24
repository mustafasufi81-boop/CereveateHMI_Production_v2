"""
Test HMI Complete Data Flow:
1. Database mapped tags
2. OPC pool values
3. Filtered display
"""
import requests
import json
import time
import psycopg2

print("=" * 80)
print("🧪 Testing HMI Complete Data Flow")
print("=" * 80)

# Test 1: Check database mapped tags
print("\n📋 Step 1: Checking database mapped tags...")
try:
    conn = psycopg2.connect(
        host="localhost",
        port=5432,
        database="Cereveate",
        user="cereveate",
        password="cereveate@222"
    )
    cursor = conn.cursor()
    cursor.execute("SELECT tag_id FROM historian_meta.tag_master WHERE enabled = true ORDER BY tag_id")
    db_tags = [row[0] for row in cursor.fetchall()]
    cursor.close()
    conn.close()
    
    print(f"   ✅ Found {len(db_tags)} enabled tags in database")
    print(f"   📝 Sample tags: {db_tags[:5]}")
    
except Exception as e:
    print(f"   ❌ Database error: {e}")
    exit(1)

# Test 2: Check HMI Flask API returns mapped tags
print("\n🌐 Step 2: Checking HMI API returns mapped tags...")
try:
    response = requests.get("http://localhost:5002/api/tags/enabled", timeout=5)
    if response.status_code == 200:
        data = response.json()
        hmi_tags = [tag['tagId'] for tag in data['tags']]
        print(f"   ✅ HMI API returned {len(hmi_tags)} tags")
        print(f"   📝 Sample: {hmi_tags[:5]}")
        
        # Verify match
        if set(hmi_tags) == set(db_tags):
            print(f"   ✅ HMI tags match database exactly!")
        else:
            print(f"   ⚠️  Tag mismatch:")
            print(f"      Missing in HMI: {set(db_tags) - set(hmi_tags)}")
            print(f"      Extra in HMI: {set(hmi_tags) - set(db_tags)}")
    else:
        print(f"   ❌ HMI API error: {response.status_code}")
        print(f"      {response.text}")
except Exception as e:
    print(f"   ❌ HMI connection error: {e}")
    print(f"   💡 Make sure HMI is running: cd HMI && python app.py")

# Test 3: Check C# OPC service pool
print("\n⚙️  Step 3: Checking C# OPC service pool...")
try:
    response = requests.get("http://localhost:5001/api/opc/values", timeout=5)
    if response.status_code == 200:
        data = response.json()
        opc_tags = [tag['tagId'] for tag in data['tags']]
        print(f"   ✅ OPC pool has {len(opc_tags)} tags")
        print(f"   📝 Sample: {opc_tags[:5]}")
        
        # Check how many mapped tags have values
        matched_tags = set(db_tags) & set(opc_tags)
        print(f"\n   🎯 Tags in both DB mapping AND OPC pool: {len(matched_tags)}/{len(db_tags)}")
        
        if len(matched_tags) > 0:
            print(f"   ✅ Found {len(matched_tags)} mapped tags with live values!")
            print(f"   📊 Sample values:")
            for tag in data['tags'][:5]:
                if tag['tagId'] in db_tags:
                    print(f"      {tag['tagId']}: {tag['value']} ({tag['quality']})")
        else:
            print(f"   ⚠️  No mapped tags found in OPC pool")
            print(f"   💡 Make sure OPC connection is active and tags are being polled")
            
        # Show unmapped tags
        missing_in_opc = set(db_tags) - set(opc_tags)
        if missing_in_opc:
            print(f"\n   ⚠️  {len(missing_in_opc)} mapped tags NOT in OPC pool:")
            for tag in list(missing_in_opc)[:5]:
                print(f"      - {tag}")
                
    else:
        print(f"   ❌ OPC API error: {response.status_code}")
        print(f"      {response.text}")
except Exception as e:
    print(f"   ❌ OPC connection error: {e}")
    print(f"   💡 Make sure C# OPC service is running")

# Test 4: Verify complete flow
print("\n" + "=" * 80)
print("📊 SUMMARY:")
print("=" * 80)

try:
    # Get all data again
    db_response = requests.get("http://localhost:5002/api/tags/enabled", timeout=5)
    opc_response = requests.get("http://localhost:5001/api/opc/values", timeout=5)
    
    if db_response.status_code == 200 and opc_response.status_code == 200:
        db_data = db_response.json()
        opc_data = opc_response.json()
        
        db_tag_ids = [tag['tagId'] for tag in db_data['tags']]
        opc_tag_ids = [tag['tagId'] for tag in opc_data['tags']]
        
        matched = set(db_tag_ids) & set(opc_tag_ids)
        
        print(f"✅ Database Mapped Tags: {len(db_tag_ids)}")
        print(f"✅ OPC Pool Tags: {len(opc_tag_ids)}")
        print(f"✅ Matched Tags (will show in HMI): {len(matched)}")
        
        if len(matched) > 0:
            print(f"\n🎉 SUCCESS! HMI will display {len(matched)} live tags")
            print(f"\n📋 Tags that will appear in HMI:")
            for tag_id in list(matched)[:10]:
                # Find value
                opc_tag = next((t for t in opc_data['tags'] if t['tagId'] == tag_id), None)
                if opc_tag:
                    print(f"   ✓ {tag_id}: {opc_tag['value']} ({opc_tag['quality']})")
            
            if len(matched) > 10:
                print(f"   ... and {len(matched) - 10} more tags")
                
            print(f"\n🌐 Open HMI: http://localhost:5002")
            
        else:
            print(f"\n⚠️  WARNING: No tags will display in HMI")
            print(f"   Reason: No overlap between database mappings and OPC pool")
            print(f"\n💡 Troubleshooting:")
            print(f"   1. Check OPC connection is active")
            print(f"   2. Verify tag names match exactly in database and OPC")
            print(f"   3. Wait 1-2 seconds for OPC pool to populate")
            
    else:
        print(f"❌ Cannot complete test - API errors")
        
except Exception as e:
    print(f"❌ Summary failed: {e}")

print("\n" + "=" * 80)
print("✅ Test Complete!")
print("=" * 80)
