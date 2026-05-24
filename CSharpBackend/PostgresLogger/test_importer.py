"""
TEST UTILITY FOR HIGH-PERFORMANCE IMPORTER
Quick validation of importer functionality
"""

import os
import sys
import logging
from pathlib import Path

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.high_performance_importer import HighPerformanceImporter
from utils.config_manager import get_config_manager
import psycopg2
from psycopg2.extras import RealDictCursor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_database_connection():
    """Test 1: Database connection"""
    print("\n" + "="*80)
    print("TEST 1: Database Connection")
    print("="*80)
    
    try:
        config = get_config_manager()
        importer = HighPerformanceImporter()
        conn = importer.get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT version();")
        version = cursor.fetchone()[0]
        print(f"✅ Connected to PostgreSQL")
        print(f"   Version: {version.split(',')[0]}")
        
        cursor.close()
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return False


def test_schema_exists():
    """Test 2: Verify schema tables exist"""
    print("\n" + "="*80)
    print("TEST 2: Schema Verification")
    print("="*80)
    
    required_tables = [
        'sensor_data',
        'tag_catalog',
        'tag_file_catalog',
        'file_imports',
        'tag_imports',
        'import_metrics',
        'tag_sampling_state'
    ]
    
    try:
        config = get_config_manager()
        importer = HighPerformanceImporter()
        conn = importer.get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT tablename 
            FROM pg_tables 
            WHERE schemaname = 'public' 
              AND tablename IN %s
        """, (tuple(required_tables),))
        
        existing_tables = [row[0] for row in cursor.fetchall()]
        
        all_exist = True
        for table in required_tables:
            if table in existing_tables:
                print(f"✅ {table}")
            else:
                print(f"❌ {table} (MISSING)")
                all_exist = False
        
        cursor.close()
        conn.close()
        
        if all_exist:
            print("\n✅ All required tables exist")
            return True
        else:
            print("\n❌ Some tables missing - run setup_importer.bat")
            return False
        
    except Exception as e:
        print(f"❌ Schema check failed: {e}")
        return False


def test_tag_mappings():
    """Test 3: Verify tag mappings configured"""
    print("\n" + "="*80)
    print("TEST 3: Tag Mappings Configuration")
    print("="*80)
    
    try:
        config = get_config_manager()
        mappings = config.get_enabled_tag_mappings()
        
        print(f"📋 Enabled tag mappings: {len(mappings)}")
        
        if len(mappings) == 0:
            print("⚠️  No tag mappings configured")
            print("   Add mappings to config/app_config.json")
            return False
        
        for i, mapping in enumerate(mappings[:5], 1):
            print(f"\n  {i}. {mapping.get('tag_name', 'Unnamed')}")
            print(f"     Column: {mapping.get('parquet_column')}")
            print(f"     Asset: {mapping.get('plant')}/{mapping.get('asset')}/{mapping.get('subsystem')}")
            print(f"     Sampling: {mapping.get('sampling_frequency_seconds', 0)}s")
        
        if len(mappings) > 5:
            print(f"\n  ... and {len(mappings) - 5} more")
        
        print(f"\n✅ {len(mappings)} tag mappings configured")
        return True
        
    except Exception as e:
        print(f"❌ Configuration check failed: {e}")
        return False


def test_parquet_files():
    """Test 4: Check parquet files exist"""
    print("\n" + "="*80)
    print("TEST 4: Parquet Files Detection")
    print("="*80)
    
    try:
        config = get_config_manager()
        data_dir = config.get_parquet_source_config().get('data_directory')
        
        print(f"📂 Data directory: {data_dir}")
        
        if not os.path.exists(data_dir):
            print(f"❌ Directory not found: {data_dir}")
            return False
        
        parquet_files = list(Path(data_dir).glob('*.parquet'))
        
        print(f"📁 Parquet files found: {len(parquet_files)}")
        
        if len(parquet_files) == 0:
            print("⚠️  No parquet files found")
            print("   Ensure OPC DA service is writing parquet files")
            return False
        
        # Show first 5 files
        for i, file_path in enumerate(parquet_files[:5], 1):
            file_size = os.path.getsize(file_path)
            print(f"  {i}. {file_path.name} ({file_size:,} bytes)")
        
        if len(parquet_files) > 5:
            print(f"  ... and {len(parquet_files) - 5} more")
        
        print(f"\n✅ {len(parquet_files)} parquet files ready for import")
        return True
        
    except Exception as e:
        print(f"❌ File check failed: {e}")
        return False


def test_import_queue():
    """Test 5: Check import queue status"""
    print("\n" + "="*80)
    print("TEST 5: Import Queue Status")
    print("="*80)
    
    try:
        config = get_config_manager()
        importer = HighPerformanceImporter()
        conn = importer.get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute("""
            SELECT status, COUNT(*) as count, SUM(file_size) as total_size
            FROM file_imports
            GROUP BY status
            ORDER BY 
                CASE status
                    WHEN 'PROCESSING' THEN 1
                    WHEN 'PENDING' THEN 2
                    WHEN 'FAILED' THEN 3
                    WHEN 'SKIPPED' THEN 4
                    WHEN 'SUCCESS' THEN 5
                END
        """)
        
        results = cursor.fetchall()
        
        if not results:
            print("ℹ️  Import queue is empty (no files processed yet)")
            print("   Run: start_importer.bat to begin import")
        else:
            print("📊 Queue Status:")
            for row in results:
                status = row['status']
                count = row['count']
                total_size = row['total_size'] or 0
                size_mb = total_size / (1024 * 1024)
                
                icon = {
                    'PROCESSING': '⚙️ ',
                    'PENDING': '⏳',
                    'SUCCESS': '✅',
                    'FAILED': '❌',
                    'SKIPPED': '⏭️ '
                }.get(status, '  ')
                
                print(f"  {icon} {status:12} : {count:5} files ({size_mb:,.2f} MB)")
        
        cursor.close()
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Queue check failed: {e}")
        return False


def test_tag_catalog():
    """Test 6: Check tag catalog"""
    print("\n" + "="*80)
    print("TEST 6: Tag Catalog Status")
    print("="*80)
    
    try:
        config = get_config_manager()
        importer = HighPerformanceImporter()
        conn = importer.get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Total tags
        cursor.execute("SELECT COUNT(*) as total FROM tag_catalog")
        total_tags = cursor.fetchone()['total']
        
        # Mapped vs unmapped
        cursor.execute("""
            SELECT 
                is_mapped,
                COUNT(*) as count
            FROM tag_catalog
            GROUP BY is_mapped
        """)
        
        results = cursor.fetchall()
        mapped_count = 0
        unmapped_count = 0
        
        for row in results:
            if row['is_mapped']:
                mapped_count = row['count']
            else:
                unmapped_count = row['count']
        
        print(f"📊 Tag Catalog:")
        print(f"  Total tags discovered: {total_tags}")
        print(f"  ✅ Mapped tags: {mapped_count}")
        print(f"  ⏸️  Unmapped tags: {unmapped_count}")
        
        if total_tags == 0:
            print("\nℹ️  Catalog is empty (no files processed yet)")
        
        cursor.close()
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Catalog check failed: {e}")
        return False


def test_sensor_data():
    """Test 7: Check sensor_data records"""
    print("\n" + "="*80)
    print("TEST 7: Sensor Data Status")
    print("="*80)
    
    try:
        config = get_config_manager()
        importer = HighPerformanceImporter()
        conn = importer.get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Total records
        cursor.execute("SELECT COUNT(*) as total FROM sensor_data")
        total_records = cursor.fetchone()['total']
        
        # Records by tag
        cursor.execute("""
            SELECT 
                tag_code,
                tag_name,
                COUNT(*) as records,
                MIN(timestamp) as first_record,
                MAX(timestamp) as last_record
            FROM sensor_data
            GROUP BY tag_code, tag_name
            ORDER BY records DESC
            LIMIT 5
        """)
        
        results = cursor.fetchall()
        
        print(f"📊 Sensor Data:")
        print(f"  Total records imported: {total_records:,}")
        
        if results:
            print(f"\n  Top Tags:")
            for row in results:
                print(f"\n    {row['tag_name'] or row['tag_code']}")
                print(f"      Records: {row['records']:,}")
                print(f"      Range: {row['first_record']} → {row['last_record']}")
        else:
            print("\nℹ️  No data imported yet")
            print("   Run: start_importer.bat to import data")
        
        cursor.close()
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Data check failed: {e}")
        return False


def run_all_tests():
    """Run all tests"""
    print("\n" + "="*80)
    print("HIGH-PERFORMANCE IMPORTER - SYSTEM TEST")
    print("="*80)
    
    tests = [
        ("Database Connection", test_database_connection),
        ("Schema Verification", test_schema_exists),
        ("Tag Mappings", test_tag_mappings),
        ("Parquet Files", test_parquet_files),
        ("Import Queue", test_import_queue),
        ("Tag Catalog", test_tag_catalog),
        ("Sensor Data", test_sensor_data)
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"\n❌ Test '{test_name}' crashed: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status} - {test_name}")
    
    print(f"\n  Total: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n✅ ALL TESTS PASSED - System ready for production")
    else:
        print(f"\n⚠️  {total - passed} test(s) failed - check configuration")
    
    print("="*80 + "\n")
    
    return passed == total


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
