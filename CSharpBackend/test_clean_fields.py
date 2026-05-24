import requests

# Login
login_response = requests.post(
    "http://localhost:6001/api/auth/login",
    json={"username": "Mustafa", "password": "Admin@123"}
)

token = login_response.json()["token"]

# Test with FTP-1/POTLINE (has 10 tags with good data)
print("=== Testing FTP-1/POTLINE (should have data) ===")
response = requests.get(
    "http://localhost:6001/api/reports/daily?date=2026-05-18&plant=FTP-1&area=POTLINE",
    headers={"Authorization": f"Bearer {token}"}
)

if response.status_code == 200:
    data = response.json()
    rows = data.get("rows", [])
    print(f"Rows returned: {len(rows)}\n")
    
    if len(rows) > 0:
        # Check first 3 rows
        for i, row in enumerate(rows[:3]):
            print(f"Row {i+1}: {row['tag_id']}")
            print(f"  sub_equipment: '{row.get('sub_equipment')}'")
            print(f"  description: '{row.get('description')}'")
            print(f"  eng_unit: '{row.get('eng_unit')}'")
            
            # Check if still showing 'None' string
            if row.get('sub_equipment') == 'None':
                print("  ❌ STILL SHOWING 'None' STRING!")
            elif not row.get('sub_equipment'):
                print("  ⚠️ Empty sub_equipment")
            else:
                print("  ✅ sub_equipment looks good")
                
            if row.get('description') == 'None':
                print("  ❌ STILL SHOWING 'None' STRING!")
            elif not row.get('description'):
                print("  ⚠️ Empty description")
            else:
                print("  ✅ description looks good")
                
            if row.get('eng_unit') == 'None':
                print("  ❌ STILL SHOWING 'None' STRING!")
            elif not row.get('eng_unit'):
                print("  ⚠️ Empty eng_unit")
            else:
                print("  ✅ eng_unit looks good")
            print()
    else:
        print("❌ No rows returned!")
        print(f"Response: {data}")
else:
    print(f"❌ Request failed: {response.status_code}")
    print(response.text)
