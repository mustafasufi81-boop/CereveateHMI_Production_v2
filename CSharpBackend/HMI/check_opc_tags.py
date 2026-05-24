#!/usr/bin/env python3
"""Check if OPC server has the same tags as database"""
import requests
import json

# Get mapped tags from database
db_tags = [
    "@ClientCount", "Bucket Brigade.Real4", "Bucket Brigade.Real8", 
    "Bucket Brigade.UInt1", "Bucket Brigade.UInt2", "Bucket Brigade.UInt4",
    "Random.Int1", "Random.Int2", "Random.Int4", "Random.Int8", "Random.Money",
    "Random.Qualities", "Random.Real4", "Random.Real8", "Random.String",
    "Random.Time", "Random.UInt1", "Random.UInt2", "Random.UInt4", "Random.UInt8",
    "Saw-toothed Waves.Int1", "Saw-toothed Waves.Int2", "Saw-toothed Waves.Int4",
    "Saw-toothed Waves.Money", "Saw-toothed Waves.Real8", "Saw-toothed Waves.UInt1",
    "Saw-toothed Waves.UInt2", "Saw-toothed Waves.UInt4", "Triangle Waves.Int1",
    "Triangle Waves.Int2", "Triangle Waves.Int4", "Triangle Waves.Real4",
    "Triangle Waves.Real8", "Triangle Waves.UInt1", "Triangle Waves.UInt2",
    "Triangle Waves.UInt4"
]

print(f"\n{'='*80}")
print(f"CHECKING OPC SERVER FOR MAPPED TAGS")
print(f"{'='*80}\n")

try:
    # Get current tag values from C# backend API
    response = requests.get('http://127.0.0.1:5001/api/historian/live', timeout=5)
    
    if response.status_code == 200:
        opc_tags = response.json()
        opc_tag_ids = [tag['tagId'] for tag in opc_tags]
        
        print(f"✅ OPC Server Response: {len(opc_tags)} tags available\n")
        
        # Check which DB tags are available in OPC
        found = []
        missing = []
        
        for db_tag in db_tags:
            if db_tag in opc_tag_ids:
                found.append(db_tag)
            else:
                missing.append(db_tag)
        
        print(f"{'='*80}")
        print(f"FOUND IN OPC: {len(found)}/{len(db_tags)} tags")
        print(f"{'='*80}\n")
        
        for i, tag in enumerate(found, 1):
            print(f"  {i:3}. ✅ {tag}")
        
        if missing:
            print(f"\n{'='*80}")
            print(f"MISSING FROM OPC: {len(missing)} tags")
            print(f"{'='*80}\n")
            
            for i, tag in enumerate(missing, 1):
                print(f"  {i:3}. ❌ {tag}")
        
        print(f"\n{'='*80}")
        print(f"Summary: {len(found)} available, {len(missing)} missing")
        print(f"{'='*80}\n")
        
    else:
        print(f"❌ Error: API returned status {response.status_code}")
        print(f"Response: {response.text}")
        
except Exception as e:
    print(f"❌ Error connecting to C# backend: {e}")
    print("\nMake sure OpcDaWebBrowser is running on port 5001")
