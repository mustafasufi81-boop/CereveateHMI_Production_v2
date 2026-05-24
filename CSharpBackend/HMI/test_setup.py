"""
Quick test script to verify HMI setup
Run this before starting the main application
"""
import sys
import json

def check_python_version():
    """Check Python version"""
    print("✓ Checking Python version...")
    if sys.version_info < (3, 8):
        print("  ❌ Python 3.8+ required")
        print(f"  Current version: {sys.version}")
        return False
    print(f"  ✅ Python {sys.version_info.major}.{sys.version_info.minor}")
    return True

def check_dependencies():
    """Check required packages"""
    print("\n✓ Checking dependencies...")
    required = [
        'flask',
        'flask_socketio',
        'flask_cors',
        'signalrcore',
        'requests',
        'psycopg2',
        'eventlet'
    ]
    
    missing = []
    for package in required:
        try:
            __import__(package)
            print(f"  ✅ {package}")
        except ImportError:
            print(f"  ❌ {package} - NOT INSTALLED")
            missing.append(package)
    
    if missing:
        print(f"\n  Run: pip install -r requirements.txt")
        return False
    
    return True

def check_config():
    """Check configuration file"""
    print("\n✓ Checking configuration...")
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
        
        required_keys = ['csharp_backend', 'hmi_server', 'database', 'performance']
        for key in required_keys:
            if key in config:
                print(f"  ✅ {key}")
            else:
                print(f"  ❌ {key} - MISSING")
                return False
        
        return True
        
    except FileNotFoundError:
        print("  ❌ config.json not found")
        return False
    except json.JSONDecodeError:
        print("  ❌ config.json is not valid JSON")
        return False

def check_csharp_backend():
    """Check if C# backend is accessible"""
    print("\n✓ Checking C# backend...")
    try:
        import requests
        with open('config.json', 'r') as f:
            config = json.load(f)
        
        host = config['csharp_backend']['host']
        port = config['csharp_backend']['port']
        url = f"http://{host}:{port}"
        
        response = requests.get(url, timeout=2)
        print(f"  ✅ C# backend accessible at {url}")
        return True
        
    except Exception as e:
        print(f"  ⚠️  C# backend not accessible")
        print(f"     Make sure OpcDaWebBrowser.exe is running on port {port}")
        return False

def check_database():
    """Check database connection"""
    print("\n✓ Checking database...")
    try:
        import psycopg2
        with open('config.json', 'r') as f:
            config = json.load(f)
        
        db = config['database']
        conn = psycopg2.connect(
            host=db['host'],
            port=db['port'],
            database=db['database'],
            user=db['user'],
            password=db['password'],
            connect_timeout=2
        )
        conn.close()
        print(f"  ✅ Database connection successful")
        return True
        
    except Exception as e:
        print(f"  ⚠️  Database not accessible: {e}")
        print(f"     Historical trends will not work")
        print(f"     Live data will still function")
        return False

def main():
    print("=" * 60)
    print("  HMI Dashboard - Pre-flight Check")
    print("=" * 60)
    
    checks = [
        ("Python Version", check_python_version()),
        ("Dependencies", check_dependencies()),
        ("Configuration", check_config()),
        ("C# Backend", check_csharp_backend()),
        ("Database", check_database())
    ]
    
    print("\n" + "=" * 60)
    print("  Summary")
    print("=" * 60)
    
    for name, result in checks:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {name:20} {status}")
    
    critical_passed = all([checks[0][1], checks[1][1], checks[2][1]])
    optional_passed = all([checks[3][1], checks[4][1]])
    
    print("\n" + "=" * 60)
    if critical_passed:
        print("  ✅ Ready to start HMI!")
        print("\n  Run: python app.py")
        if not optional_passed:
            print("\n  ⚠️  Some optional features may not work:")
            if not checks[3][1]:
                print("     - C# backend not running (start OpcDaWebBrowser.exe)")
            if not checks[4][1]:
                print("     - Database not available (historical trends disabled)")
    else:
        print("  ❌ Critical checks failed")
        print("\n  Fix the issues above before starting")
    print("=" * 60)

if __name__ == '__main__':
    main()
