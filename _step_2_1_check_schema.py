"""
Step 2.1: Check Current Database Schema for alarm_audit_trail
Verifies columns, indexes, and prepares for updates
"""
import psycopg2
import sys

def check_schema():
    try:
        # Connect to database
        conn = psycopg2.connect(
            dbname='Automation_DB',
            user='cereveate',
            password='cereveate@222',
            host='localhost',
            port=5432  # Standard PostgreSQL port
        )
        cur = conn.cursor()
        
        print("=" * 80)
        print("STEP 2.1: Database Schema Check")
        print("=" * 80)
        
        # Check if table exists
        cur.execute("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables 
                WHERE table_schema = 'historian_raw' 
                  AND table_name = 'alarm_audit_trail'
            )
        """)
        table_exists = cur.fetchone()[0]
        
        if not table_exists:
            print("\n❌ ERROR: alarm_audit_trail table does not exist!")
            cur.close()
            conn.close()
            return False
        
        print("\n✅ Table historian_raw.alarm_audit_trail exists\n")
        
        # Get all columns
        cur.execute("""
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns 
            WHERE table_schema = 'historian_raw' 
              AND table_name = 'alarm_audit_trail'
            ORDER BY ordinal_position
        """)
        columns = cur.fetchall()
        
        print("Current Columns:")
        print("-" * 80)
        print(f"{'Column Name':<35} {'Data Type':<20} {'Nullable':<10} {'Default'}")
        print("-" * 80)
        
        column_names = []
        for col in columns:
            col_name, data_type, nullable, default = col
            column_names.append(col_name)
            default_str = str(default)[:30] if default else 'None'
            print(f"{col_name:<35} {data_type:<20} {nullable:<10} {default_str}")
        
        # Check for required new columns
        print("\n" + "=" * 80)
        print("Required Columns Check:")
        print("=" * 80)
        
        required_columns = {
            'occurrence_id': 'uuid',
            'sequence_number': 'integer',
            'performed_by_display_name': 'text',
            'performed_by_user_id': 'integer'
        }
        
        missing_columns = []
        for col_name, col_type in required_columns.items():
            if col_name in column_names:
                print(f"✅ {col_name:<35} EXISTS")
            else:
                print(f"❌ {col_name:<35} MISSING (will be added)")
                missing_columns.append((col_name, col_type))
        
        # Check existing indexes
        cur.execute("""
            SELECT indexname, indexdef 
            FROM pg_indexes 
            WHERE schemaname = 'historian_raw' 
              AND tablename = 'alarm_audit_trail'
            ORDER BY indexname
        """)
        indexes = cur.fetchall()
        
        print("\n" + "=" * 80)
        print("Current Indexes:")
        print("=" * 80)
        
        if indexes:
            for idx_name, idx_def in indexes:
                print(f"\n{idx_name}:")
                print(f"  {idx_def}")
        else:
            print("No indexes found (besides primary key)")
        
        # Check for required indexes
        print("\n" + "=" * 80)
        print("Required Indexes Check:")
        print("=" * 80)
        
        index_names = [idx[0] for idx in indexes]
        
        required_indexes = [
            'idx_alarm_audit_event_timestamp',
            'idx_alarm_audit_occurrence',
            'idx_alarm_audit_event_sequence'
        ]
        
        missing_indexes = []
        for idx_name in required_indexes:
            if idx_name in index_names:
                print(f"✅ {idx_name:<45} EXISTS")
            else:
                print(f"❌ {idx_name:<45} MISSING (will be created)")
                missing_indexes.append(idx_name)
        
        # Summary
        print("\n" + "=" * 80)
        print("SUMMARY:")
        print("=" * 80)
        print(f"Total columns: {len(column_names)}")
        print(f"Missing columns: {len(missing_columns)}")
        print(f"Total indexes: {len(indexes)}")
        print(f"Missing indexes: {len(missing_indexes)}")
        
        if missing_columns or missing_indexes:
            print("\n⚠️  Schema updates required")
            print("\nMissing columns to add:")
            for col_name, col_type in missing_columns:
                print(f"  - {col_name} ({col_type})")
            if missing_indexes:
                print("\nMissing indexes to create:")
                for idx in missing_indexes:
                    print(f"  - {idx}")
        else:
            print("\n✅ Schema is complete - no updates needed")
        
        cur.close()
        conn.close()
        
        return True
        
    except psycopg2.OperationalError as e:
        print(f"\n❌ Database connection error: {e}")
        print("\n💡 Trying alternate port 5433...")
        
        try:
            # Try port 5433
            conn = psycopg2.connect(
                dbname='Automation_DB',
                user='cereveate',
                password='cereveate@222',
                host='localhost',
                port=5433
            )
            print("✅ Connected on port 5433")
            conn.close()
            print("\n⚠️  Please update the script to use port 5433")
            return False
        except:
            print("❌ Port 5433 also failed")
            print("\n📝 Action required:")
            print("  1. Check if PostgreSQL is running")
            print("  2. Verify connection parameters")
            print("  3. Check firewall settings")
            return False
    
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    success = check_schema()
    sys.exit(0 if success else 1)
