"""Check what the Flask API is actually returning"""
import requests
import json

# Get a real token first by logging in
login_url = "http://localhost:6001/api/auth/login"
login_data = {
    "username": "Mustafa",
    "password": "Admin@123"
}

print("=== Step 1: Login to get token ===")
response = requests.post(login_url, json=login_data)
print(f"Login Status: {response.status_code}")

if response.status_code == 200:
    token = response.json().get("token")
    print(f"Token obtained: {token[:50]}...")
    
    # Now call the daily report API
    print("\n=== Step 2: Call daily report API ===")
    report_url = "http://localhost:6001/api/reports/daily"
    params = {
        "date": "2026-05-18",
        "plant": "FTP-1,PLANT_001,Plant1",
        "area": "AREA_A,Area-2,Area1,POTLINE,Production",
        "page": "1",
        "page_size": "500"
    }
    headers = {
        "Authorization": f"Bearer {token}"
    }
    
    print(f"URL: {report_url}")
    print(f"Params: {json.dumps(params, indent=2)}")
    
    response = requests.get(report_url, params=params, headers=headers)
    print(f"\nResponse Status: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        
        # Check the structure
        print(f"\n=== Response Structure ===")
        print(f"Keys in response: {list(data.keys())}")
        
        if 'meta' in data:
            print(f"\nMeta:")
            print(f"  Company: {data['meta'].get('company')}")
            print(f"  Plant: {data['meta'].get('plant')}")
            print(f"  Report Title: {data['meta'].get('report_title')}")
            print(f"  Date: {data['meta'].get('date')}")
        
        if 'columns' in data:
            print(f"\nColumns: {len(data['columns'])} items")
            print(f"  First 3: {data['columns'][:3]}")
        
        if 'rows' in data:
            print(f"\nRows: {len(data['rows'])} tags")
            
            if data['rows']:
                print(f"\n=== First 5 rows ===")
                for i, row in enumerate(data['rows'][:5]):
                    print(f"\nRow {i+1}:")
                    print(f"  tag_id: {row.get('tag_id')}")
                    print(f"  display_label: {row.get('display_label')}")
                    print(f"  group: {row.get('group')}")
                    print(f"  sub_equipment: {row.get('sub_equipment')}")
                    print(f"  description: {row.get('description')}")
                    print(f"  eng_unit: {row.get('eng_unit')}")
                    print(f"  avg: {row.get('avg')}")
                    print(f"  max: {row.get('max')}")
                    print(f"  min: {row.get('min')}")
                    
                    hourly = row.get('hourly', [])
                    non_null = [h for h in hourly if h is not None]
                    print(f"  hourly: {len(hourly)} total, {len(non_null)} non-null")
                    if non_null:
                        print(f"    Sample values: {non_null[:3]}")
                
                # Count tags with data
                tags_with_data = sum(1 for row in data['rows'] if any(h is not None for h in row.get('hourly', [])))
                tags_without_data = len(data['rows']) - tags_with_data
                
                print(f"\n=== Summary ===")
                print(f"Total rows: {len(data['rows'])}")
                print(f"Tags WITH data: {tags_with_data}")
                print(f"Tags WITHOUT data: {tags_without_data}")
            else:
                print("❌ NO ROWS IN RESPONSE!")
        
        if 'pagination' in data:
            print(f"\nPagination:")
            print(f"  page: {data['pagination'].get('page')}")
            print(f"  page_size: {data['pagination'].get('page_size')}")
            print(f"  total_rows: {data['pagination'].get('total_rows')}")
            print(f"  total_pages: {data['pagination'].get('total_pages')}")
    else:
        print(f"Error: {response.text}")
else:
    print(f"Login failed: {response.text}")
