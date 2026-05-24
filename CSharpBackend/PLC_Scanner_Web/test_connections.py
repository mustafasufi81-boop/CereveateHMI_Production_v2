#!/usr/bin/env python3
"""
Test PLC and Database connections for plc_scanner_web.py
"""

import sys
import psycopg2

# PLC Configuration
PLC_IP = "192.168.0.20"
PLC_PATH = f"{PLC_IP}/1,0"  # Correct format for pycomm3

# Database Configuration
DB_CONFIG = {
    'host': '192.168.0.120',
    'port': 5432,
    'database': 'Cereveate',
    'user': 'cereveate',
    'password': 'cereveate@222',
    'sslmode': 'disable',
    'connect_timeout': 5
}

def test_plc_connection():
    """Test PLC connection using correct pycomm3 syntax"""
    print("\n" + "="*60)
    print("TEST 1: PLC CONNECTION")
    print("="*60)
    
    try:
        from pycomm3 import LogixDriver
        print(f"✓ pycomm3 imported successfully")
    except ImportError as e:
        print(f"✗ Failed to import pycomm3: {e}")
        print("  Install with: pip install pycomm3")
        return False
    
    print(f"PLC Path: {PLC_PATH}")
    print(f"Attempting connection...")
    
    try:
        with LogixDriver(PLC_PATH) as plc:
            print(f"✓ Connected to PLC at {PLC_PATH}")
            
            # Try to read a test tag
            try:
                tags = plc.get_tag_list()
                print(f"✓ Read tag list: {len(tags)} tags found")
                
                # Show first 5 tags
                if tags:
                    print(f"  First 5 tags:")
                    for i, tag in enumerate(tags[:5]):
                        name = getattr(tag, "tag_name", None) or tag.get("tag_name")
                        print(f"    {i+1}. {name}")
                
                return True
            except Exception as e:
                print(f"✗ Failed to read tags: {e}")
                return False
                
    except Exception as e:
        print(f"✗ PLC Connection Failed: {e}")
        print(f"  Check:")
        print(f"    - PLC IP: {PLC_IP} is reachable")
        print(f"    - PLC is online and accessible")
        print(f"    - Network connectivity")
        return False

def test_database_connection():
    """Test PostgreSQL database connection"""
    print("\n" + "="*60)
    print("TEST 2: DATABASE CONNECTION")
    print("="*60)
    
    print(f"Database: {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}")
    print(f"User: {DB_CONFIG['user']}")
    print(f"Attempting connection...")
    
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        print(f"✓ Connected to database successfully")
        
        # Test query
        with conn.cursor() as cur:
            cur.execute("SELECT version()")
            version = cur.fetchone()[0]
            print(f"✓ Database version: {version[:50]}...")
            
            # Check for historian tables
            cur.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'historian_raw' 
                ORDER BY table_name
            """)
            tables = cur.fetchall()
            print(f"✓ Found {len(tables)} historian_raw tables:")
            for table in tables:
                print(f"    - {table[0]}")
            
            # Check tag_master table
            cur.execute("""
                SELECT COUNT(*) 
                FROM historian_meta.tag_master 
                WHERE enabled = true
            """)
            count = cur.fetchone()[0]
            print(f"✓ Found {count} enabled tags in tag_master")
            
        conn.close()
        return True
        
    except Exception as e:
        print(f"✗ Database Connection Failed: {e}")
        print(f"  Check:")
        print(f"    - Database server {DB_CONFIG['host']} is running")
        print(f"    - Port {DB_CONFIG['port']} is accessible")
        print(f"    - Credentials are correct")
        print(f"    - Database '{DB_CONFIG['database']}' exists")
        return False

def main():
    print("\n" + "="*60)
    print("PLC SCANNER WEB - CONNECTION TEST")
    print("="*60)
    
    plc_ok = test_plc_connection()
    db_ok = test_database_connection()
    
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"PLC Connection:      {'✓ PASS' if plc_ok else '✗ FAIL'}")
    print(f"Database Connection: {'✓ PASS' if db_ok else '✗ FAIL'}")
    print("="*60)
    
    if plc_ok and db_ok:
        print("\n✓ All tests passed! Ready to run plc_scanner_web.py")
        return 0
    else:
        print("\n✗ Some tests failed. Fix errors before running plc_scanner_web.py")
        return 1

if __name__ == '__main__':
    sys.exit(main())
