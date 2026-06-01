"""
Test the actual audit trail API response order
"""
import requests
import json

API_BASE = "http://localhost:8090"
alarm_id = 881456

print("\n" + "="*80)
print(f"Testing Audit Trail API Order for Event {alarm_id}")
print("="*80 + "\n")

try:
    # Login
    resp = requests.post(f"{API_BASE}/api/auth/login", json={"username": "admin", "password": "admin123"}, timeout=5)
    if resp.status_code == 200:
        token = resp.json().get('access_token')
        headers = {"Authorization": f"Bearer {token}"}
        
        # Get audit trail
        resp = requests.get(f"{API_BASE}/api/alarms/audit/{alarm_id}", headers=headers, timeout=5)
        
        if resp.status_code == 200:
            data = resp.json()
            audit_trail = data.get('audit_trail', [])
            
            print(f"Total records: {len(audit_trail)}\n")
            print("First 5 records (should be NEWEST first):")
            print("-" * 80)
            
            for i, record in enumerate(audit_trail[:5], 1):
                action = record.get('action_type', 'N/A')
                timestamp = record.get('action_timestamp', 'N/A')
                print(f"{i}. {action:15} | {timestamp}")
            
            print("\n" + "-" * 80)
            print("\nLast 3 records (should be OLDEST):")
            print("-" * 80)
            
            for i, record in enumerate(audit_trail[-3:], len(audit_trail)-2):
                action = record.get('action_type', 'N/A')
                timestamp = record.get('action_timestamp', 'N/A')
                print(f"{i}. {action:15} | {timestamp}")
            
            print("\n" + "="*80)
            
            # Check order
            timestamps = [r.get('action_timestamp') for r in audit_trail if r.get('action_timestamp')]
            is_desc = all(timestamps[i] >= timestamps[i+1] for i in range(len(timestamps)-1))
            is_asc = all(timestamps[i] <= timestamps[i+1] for i in range(len(timestamps)-1))
            
            print("\nORDER CHECK:")
            if is_desc:
                print("✅ CORRECT: Descending order (newest first)")
            elif is_asc:
                print("❌ WRONG: Ascending order (oldest first)")
            else:
                print("❌ MIXED: Order is inconsistent")
            
            print("="*80 + "\n")
        else:
            print(f"❌ API error: {resp.status_code}")
            print(resp.text)
    else:
        print(f"❌ Login failed: {resp.status_code}")
        
except Exception as e:
    print(f"❌ Error: {e}")
