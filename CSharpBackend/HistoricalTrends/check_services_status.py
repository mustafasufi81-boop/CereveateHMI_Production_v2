"""
Check status of all background services
"""
import subprocess
import requests
import json
from pathlib import Path

print("=" * 70)
print("BACKGROUND SERVICES STATUS CHECK")
print("=" * 70)

# Check 1: ML Background Service
print("\n[1] ML Background Learning Service:")
try:
    result = subprocess.run(
        ['sc', 'query', 'MLBackgroundLearningSystem'],
        capture_output=True,
        text=True
    )
    if result.returncode == 0:
        if 'RUNNING' in result.stdout:
            print("   ✅ Status: RUNNING")
        elif 'STOPPED' in result.stdout:
            print("   ⚠️  Status: STOPPED (run: sc start MLBackgroundLearningSystem)")
        else:
            print("   ⚠️  Status: UNKNOWN")
    else:
        print("   ❌ Status: NOT INSTALLED")
        print("   Run: cd ML_System && python ml_background_service.py install")
except Exception as e:
    print(f"   ❌ Error checking service: {e}")

# Check 2: Flask Web Server
print("\n[2] Flask Web Server (port 5002):")
try:
    response = requests.get('http://127.0.0.1:5002/api/health', timeout=2)
    if response.status_code == 200:
        print("   ✅ Status: RUNNING")
        print(f"   URL: http://127.0.0.1:5002")
    else:
        print(f"   ⚠️  Status: Running but health check failed ({response.status_code})")
except requests.exceptions.ConnectionError:
    print("   ❌ Status: NOT RUNNING")
    print("   Run: python app.py")
except Exception as e:
    print(f"   ❌ Error: {e}")

# Check 3: Downtime Tracking Config
print("\n[3] Downtime Tracking Configuration:")
config_path = Path('baseline_config.json')
if config_path.exists():
    with open(config_path, 'r') as f:
        config = json.load(f)
    
    dt_config = config.get('downtime_tracking', {})
    if dt_config.get('enabled', False):
        print("   ✅ Enabled: YES")
        print(f"   Threshold: {dt_config.get('zero_load_threshold_mw', 1.0)} MW")
        print(f"   Min Duration: {dt_config.get('min_downtime_duration_minutes', 5)} minutes")
        print(f"   Storage: {dt_config.get('storage_directory', 'Not set')}")
    else:
        print("   ⚠️  Enabled: NO")
else:
    print("   ❌ Config file not found: baseline_config.json")

# Check 4: Storage Directories
print("\n[4] Storage Directories:")
dirs_to_check = [
    ('Data Logs', 'D:/OpcLogs/Data'),
    ('Downtime Logs', 'D:/OpcLogs/Downtime'),
    ('ML Storage', 'D:/OpcLogs/ML_Storage'),
]

for name, path in dirs_to_check:
    p = Path(path)
    if p.exists():
        file_count = len(list(p.glob('*')))
        print(f"   ✅ {name}: {path} ({file_count} files)")
    else:
        print(f"   ⚠️  {name}: {path} (NOT EXISTS)")

# Check 5: API Endpoints
print("\n[5] Downtime API Endpoints:")
try:
    response = requests.get('http://127.0.0.1:5002/api/downtime/categories', timeout=2)
    if response.status_code == 200:
        categories = response.json()
        print(f"   ✅ API Working: {len(categories)} failure categories configured")
    else:
        print(f"   ⚠️  API returned: {response.status_code}")
except requests.exceptions.ConnectionError:
    print("   ❌ Cannot reach API (Flask not running)")
except Exception as e:
    print(f"   ❌ Error: {e}")

print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)
print("""
✅ = Working correctly
⚠️  = Needs attention
❌ = Not working / Not installed

To start all services:
  Run: START_ALL_SERVICES.bat (as Administrator)

To manually start ML service:
  sc start MLBackgroundLearningSystem

To manually start Flask:
  python app.py
""")
