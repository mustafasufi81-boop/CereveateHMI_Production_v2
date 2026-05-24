"""Test the exact API call that the frontend makes"""
import requests
from datetime import datetime

# Test with the exact parameters from the UI
url = "http://localhost:6001/api/reports/daily"
params = {
    "date": "2026-05-18",
    "plant": "FTP-1,PLANT_001,Plant1",
    "area": "AREA_A,Area-2,Area1,POTLINE,Production",
    "page": "1",
    "page_size": "1000"
}

headers = {
    "Authorization": "Bearer dummy"  # from test context
}

print(f"Calling: {url}")
print(f"Params: {params}")
print()

response = requests.get(url, params=params, headers=headers)
print(f"Status Code: {response.status_code}")
print()

if response.status_code == 200:
    data = response.json()
    print(f"Success: {data.get('success', False)}")
    print(f"Message: {data.get('message', 'N/A')}")
    
    if 'data' in data:
        report = data['data']
        print(f"\nReport Meta:")
        print(f"  Company: {report['meta']['company']}")
        print(f"  Plant: {report['meta']['plant']}")
        print(f"  Title: {report['meta']['report_title']}")
        print(f"  Date: {report['meta']['date']}")
        
        print(f"\nColumns: {len(report['columns'])} hours")
        print(f"First 3 columns: {report['columns'][:3]}")
        
        print(f"\nRows: {len(report['rows'])} tags")
        print(f"\nPagination:")
        print(f"  Page: {report['pagination']['page']}")
        print(f"  Total rows: {report['pagination']['total_rows']}")
        print(f"  Total pages: {report['pagination']['total_pages']}")
        
        if report['rows']:
            print(f"\nFirst 3 rows:")
            for i, row in enumerate(report['rows'][:3]):
                print(f"\n  Row {i+1}:")
                print(f"    Tag: {row['tag_id']}")
                print(f"    Label: {row['display_label']}")
                print(f"    Group: {row['group']}")
                print(f"    Unit: {row['parameter_unit']}")
                print(f"    AVG: {row['avg']}")
                print(f"    MAX: {row['max']}")
                print(f"    MIN: {row['min']}")
                non_null_hours = [h for h in row['hourly'] if h is not None]
                print(f"    Hourly values: {len(non_null_hours)} non-null out of {len(row['hourly'])}")
                if non_null_hours:
                    print(f"    Sample values: {non_null_hours[:3]}")
        else:
            print("\n⚠️ NO ROWS RETURNED!")
            
else:
    print(f"Error: {response.text}")
