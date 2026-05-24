import requests
import json

# Test daily report API
url = "http://localhost:6001/api/reports/daily?report_date=2026-05-18&plant=FTP-1&area=ESP"

headers = {
    "Content-Type": "application/json",
    "Authorization": "Bearer dummy"
}

print("Testing daily report API for Excel fields...")
response = requests.get(url, headers=headers)

if response.status_code == 200:
    data = response.json()
    if data.get("success") and "rows" in data:
        rows = data["rows"]
        print(f"\nTotal rows returned: {len(rows)}")
        
        # Check first few rows for new fields
        print("\n=== Checking New Fields (sub_equipment, description, eng_unit) ===")
        for i, row in enumerate(rows[:5]):
            tag_id = row.get("tag_id", "?")
            sub_eq = row.get("sub_equipment", "MISSING")
            desc = row.get("description", "MISSING")
            unit = row.get("eng_unit", "MISSING")
            
            print(f"\nRow {i+1}: {tag_id}")
            print(f"  sub_equipment: '{sub_eq}'")
            print(f"  description: '{desc}'")
            print(f"  eng_unit: '{unit}'")
            
            # Check if any are None or empty
            if sub_eq in [None, "", "MISSING"]:
                print(f"  ⚠️ sub_equipment is blank!")
            if desc in [None, "", "MISSING"]:
                print(f"  ⚠️ description is blank!")
            if unit in [None, "", "MISSING"]:
                print(f"  ⚠️ eng_unit is blank!")
        
        # Check if ALL rows have these fields
        missing_sub = sum(1 for r in rows if not r.get("sub_equipment"))
        missing_desc = sum(1 for r in rows if not r.get("description"))
        missing_unit = sum(1 for r in rows if not r.get("eng_unit"))
        
        print(f"\n=== Summary for {len(rows)} rows ===")
        print(f"Missing sub_equipment: {missing_sub} rows")
        print(f"Missing description: {missing_desc} rows")
        print(f"Missing eng_unit: {missing_unit} rows")
        
        if missing_sub == 0 and missing_desc == 0 and missing_unit == 0:
            print("\n✅ ALL FIELDS PRESENT! Excel should work now.")
        else:
            print("\n❌ Some fields still missing - backend may not be returning data correctly")
    else:
        print(f"❌ API returned success=False or no rows: {data}")
else:
    print(f"❌ API request failed: {response.status_code}")
    print(response.text)
