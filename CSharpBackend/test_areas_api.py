import requests
import json

# Test the areas endpoint directly
print("=" * 80)
print("TESTING /api/reports/areas ENDPOINT")
print("=" * 80)

# First, login to get a valid token
login_url = "http://localhost:6001/api/auth/login"
login_data = {
    "username": "Mustafa",
    "password": "Admin@123"
}

print("\n1. Logging in...")
login_response = requests.post(login_url, json=login_data)
print(f"Login status: {login_response.status_code}")

if login_response.status_code == 200:
    token = login_response.json().get("token")
    print(f"✅ Got token: {token[:50]}...")
    
    # Now call the areas endpoint
    areas_url = "http://localhost:6001/api/reports/areas"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    print("\n2. Calling /api/reports/areas...")
    areas_response = requests.get(areas_url, headers=headers)
    print(f"Status: {areas_response.status_code}")
    
    if areas_response.status_code == 200:
        data = areas_response.json()
        areas = data.get("areas", [])
        print(f"\n3. RESULT: {len(areas)} areas returned")
        print("\n4. SAMPLE DATA:")
        print(json.dumps(areas[:10], indent=2))
        
        # Check for server_progid
        has_progid = all('server_progid' in area for area in areas)
        print(f"\n5. All areas have 'server_progid' field: {has_progid}")
        
        # Show unique sources
        sources = set(area.get('server_progid') for area in areas)
        print(f"\n6. UNIQUE SOURCES ({len(sources)}):")
        for src in sorted(sources):
            print(f"   - {src}")
    else:
        print(f"❌ Error: {areas_response.text}")
else:
    print(f"❌ Login failed: {login_response.text}")

print("\n" + "=" * 80)
print("TEST COMPLETE")
print("=" * 80)
