import requests
import json

try:
    response = requests.get('http://localhost:5002/api/tags/enabled')
    print(f"Status Code: {response.status_code}")
    print(f"Response:")
    print(json.dumps(response.json(), indent=2))
except Exception as e:
    print(f"Error: {e}")
