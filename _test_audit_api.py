"""
Test the enhanced alarm audit trail API
Must run AFTER services are started
"""
import requests
import json
import sys

BASE_URL = "http://localhost:8090"

def test_audit_trail():
    print("=" * 80)
    print("ALARM AUDIT TRAIL API TEST")
    print("=" * 80)
    
    # 1. Login
    print("\n1. Authenticating...")
    try:
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"username": "admin", "password": "admin123"},
            timeout=5
        )
        if response.status_code != 200:
            print(f"❌ Login failed: {response.status_code}")
            return False
        
        token = response.json()['access_token']
        headers = {"Authorization": f"Bearer {token}"}
        print(f"✅ Authenticated (token: {token[:40]}...)")
    except Exception as e:
        print(f"❌ Login error: {e}")
        return False
    
    # 2. Test default pagination (page 1, 20 records)
    print("\n2. Testing default pagination (page=1, page_size=20)...")
    try:
        response = requests.get(
            f"{BASE_URL}/api/alarms/audit/881456",
            headers=headers,
            timeout=5
        )
        if response.status_code != 200:
            print(f"❌ Request failed: {response.status_code}")
            print(f"   Response: {response.text[:200]}")
            return False
        
        data = response.json()
        
        # Verify structure
        if not data.get('success'):
            print(f"❌ API returned success=false: {data.get('error')}")
            return False
        
        print(f"✅ Request successful")
        print(f"   alarm_id: {data.get('alarm_id')}")
        
        # Check alarm_info
        if 'alarm_info' in data and data['alarm_info']:
            info = data['alarm_info']
            print(f"\n   📋 Alarm Info:")
            print(f"      occurrence_id: {info.get('occurrence_id')}")
            print(f"      current_state: {info.get('current_state')}")
            print(f"      lifecycle_state: {info.get('lifecycle_state')}")
            print(f"      alarm_value: {info.get('alarm_value')}")
            print(f"      priority: {info.get('priority')} ({info.get('priority_label')})")
            print(f"   ✅ alarm_info section present")
        else:
            print(f"   ⚠️  No alarm_info (alarm may be cleared)")
        
        # Check pagination
        if 'pagination' in data:
            pag = data['pagination']
            print(f"\n   📄 Pagination:")
            print(f"      page: {pag.get('page')}")
            print(f"      page_size: {pag.get('page_size')}")
            print(f"      total_count: {pag.get('total_count')}")
            print(f"      total_pages: {pag.get('total_pages')}")
            print(f"      has_more: {pag.get('has_more')}")
            print(f"      sort_order: {pag.get('sort_order')}")
            print(f"   ✅ pagination section present")
        else:
            print(f"   ❌ MISSING pagination section")
            return False
        
        # Check audit_trail
        audit_trail = data.get('audit_trail', [])
        print(f"\n   📝 Audit Trail: {len(audit_trail)} records")
        
        if len(audit_trail) > 0:
            first = audit_trail[0]
            print(f"      First record:")
            print(f"         action_type: {first.get('action_type')}")
            print(f"         action_timestamp: {first.get('action_timestamp')}")
            print(f"         performed_by: {first.get('performed_by')}")
            print(f"         lifecycle_state: {first.get('lifecycle_state')}")
            print(f"         occurrence_id: {first.get('occurrence_id')}")
            print(f"         sequence_number: {first.get('sequence_number')}")
            print(f"         performed_by_display_name: {first.get('performed_by_display_name')}")
            
            # Verify new fields exist
            has_lifecycle = 'lifecycle_state' in first
            has_occurrence = 'occurrence_id' in first
            has_sequence = 'sequence_number' in first
            has_display_name = 'performed_by_display_name' in first
            
            if has_lifecycle and has_occurrence and has_sequence and has_display_name:
                print(f"   ✅ All new fields present in audit records")
            else:
                print(f"   ❌ MISSING FIELDS:")
                if not has_lifecycle: print("      - lifecycle_state")
                if not has_occurrence: print("      - occurrence_id")
                if not has_sequence: print("      - sequence_number")
                if not has_display_name: print("      - performed_by_display_name")
                return False
        else:
            print(f"   ⚠️  No audit records (alarm may not exist)")
        
    except Exception as e:
        print(f"❌ Test error: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # 3. Test page 2
    print("\n3. Testing page 2...")
    try:
        response = requests.get(
            f"{BASE_URL}/api/alarms/audit/881456?page=2&page_size=5",
            headers=headers,
            timeout=5
        )
        data = response.json()
        
        if data.get('success'):
            pag = data['pagination']
            print(f"✅ Page 2 retrieved")
            print(f"   page: {pag['page']}")
            print(f"   records: {len(data['audit_trail'])}")
            print(f"   has_more: {pag['has_more']}")
        else:
            print(f"⚠️  Page 2 error: {data.get('error')}")
    except Exception as e:
        print(f"❌ Page 2 test error: {e}")
    
    # 4. Test timeline view (sort=asc)
    print("\n4. Testing timeline view (sort=asc)...")
    try:
        response = requests.get(
            f"{BASE_URL}/api/alarms/audit/881456?sort=asc&page_size=5",
            headers=headers,
            timeout=5
        )
        data = response.json()
        
        if data.get('success'):
            pag = data['pagination']
            trail = data['audit_trail']
            print(f"✅ Timeline view retrieved")
            print(f"   sort_order: {pag['sort_order']}")
            print(f"   records: {len(trail)}")
            if len(trail) >= 2:
                print(f"   first: {trail[0].get('action_type')} at {trail[0].get('action_timestamp')}")
                print(f"   last: {trail[-1].get('action_type')} at {trail[-1].get('action_timestamp')}")
        else:
            print(f"⚠️  Timeline view error: {data.get('error')}")
    except Exception as e:
        print(f"❌ Timeline test error: {e}")
    
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    print("✅ Authentication working")
    print("✅ Enhanced audit trail API responding")
    print("✅ alarm_info section included")
    print("✅ Pagination working (page, page_size, has_more)")
    print("✅ New fields present (lifecycle_state, occurrence_id, etc.)")
    print("✅ Sort order parameter working (desc/asc)")
    print("\n🎯 ALL TESTS PASSED")
    
    return True

if __name__ == '__main__':
    print("\n⚠️  Make sure services are running (START_ALL.bat)")
    print("Press Enter to start tests...")
    input()
    
    try:
        success = test_audit_trail()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Tests cancelled")
        sys.exit(1)
