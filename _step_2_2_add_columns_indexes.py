"""
Step 2.2: Add Missing Columns and Indexes to alarm_audit_trail
Adds occurrence_id, sequence_number, operator snapshots, and performance indexes
"""
import psycopg2
import sys

def add_columns_and_indexes():
    try:
        # Connect to database
        conn = psycopg2.connect(
            dbname='Automation_DB',
            user='cereveate',
            password='cereveate@222',
            host='localhost',
            port=5432
        )
        conn.autocommit = False  # Use transactions
        cur = conn.cursor()
        
        print("=" * 80)
        print("STEP 2.2: Add Missing Columns and Indexes")
        print("=" * 80)
        
        changes_made = []
        
        # ===== ADD COLUMNS =====
        print("\n📝 Adding Missing Columns...")
        print("-" * 80)
        
        # 1. Add occurrence_id column
        try:
            cur.execute("""
                SELECT 1 FROM information_schema.columns 
                WHERE table_schema='historian_raw' 
                  AND table_name='alarm_audit_trail' 
                  AND column_name='occurrence_id'
            """)
            if not cur.fetchone():
                cur.execute("""
                    ALTER TABLE historian_raw.alarm_audit_trail 
                    ADD COLUMN occurrence_id UUID
                """)
                print("✅ Added occurrence_id column (UUID)")
                changes_made.append("Added occurrence_id column")
            else:
                print("⏭️  occurrence_id column already exists")
        except Exception as e:
            print(f"❌ Error adding occurrence_id: {e}")
            conn.rollback()
            return False
        
        # 2. Add sequence_number column
        try:
            cur.execute("""
                SELECT 1 FROM information_schema.columns 
                WHERE table_schema='historian_raw' 
                  AND table_name='alarm_audit_trail' 
                  AND column_name='sequence_number'
            """)
            if not cur.fetchone():
                cur.execute("""
                    ALTER TABLE historian_raw.alarm_audit_trail 
                    ADD COLUMN sequence_number INTEGER
                """)
                print("✅ Added sequence_number column (INTEGER)")
                changes_made.append("Added sequence_number column")
            else:
                print("⏭️  sequence_number column already exists")
        except Exception as e:
            print(f"❌ Error adding sequence_number: {e}")
            conn.rollback()
            return False
        
        # 3. Add operator snapshot columns
        try:
            cur.execute("""
                SELECT 1 FROM information_schema.columns 
                WHERE table_schema='historian_raw' 
                  AND table_name='alarm_audit_trail' 
                  AND column_name='performed_by_display_name'
            """)
            if not cur.fetchone():
                cur.execute("""
                    ALTER TABLE historian_raw.alarm_audit_trail 
                    ADD COLUMN performed_by_display_name TEXT,
                    ADD COLUMN performed_by_user_id INTEGER
                """)
                print("✅ Added performed_by_display_name column (TEXT)")
                print("✅ Added performed_by_user_id column (INTEGER)")
                changes_made.append("Added operator snapshot columns")
            else:
                print("⏭️  operator snapshot columns already exist")
        except Exception as e:
            print(f"❌ Error adding operator columns: {e}")
            conn.rollback()
            return False
        
        # Commit column additions
        conn.commit()
        print("\n✅ All columns added successfully")
        
        # ===== ADD INDEXES =====
        print("\n📊 Creating Performance Indexes...")
        print("-" * 80)
        
        # 4. Index on (event_id, action_timestamp DESC)
        try:
            cur.execute("""
                SELECT 1 FROM pg_indexes 
                WHERE schemaname='historian_raw' 
                  AND tablename='alarm_audit_trail'
                  AND indexname='idx_alarm_audit_event_timestamp'
            """)
            if not cur.fetchone():
                print("Creating idx_alarm_audit_event_timestamp...")
                cur.execute("""
                    CREATE INDEX idx_alarm_audit_event_timestamp 
                    ON historian_raw.alarm_audit_trail(event_id, action_timestamp DESC)
                """)
                cur.execute("""
                    COMMENT ON INDEX historian_raw.idx_alarm_audit_event_timestamp IS 
                    'Performance index for fetching audit trail by event_id with descending timestamp order'
                """)
                print("✅ Created idx_alarm_audit_event_timestamp")
                changes_made.append("Created idx_alarm_audit_event_timestamp")
            else:
                print("⏭️  idx_alarm_audit_event_timestamp already exists")
        except Exception as e:
            print(f"❌ Error creating event_timestamp index: {e}")
            conn.rollback()
            return False
        
        # 5. Index on occurrence_id
        try:
            cur.execute("""
                SELECT 1 FROM pg_indexes 
                WHERE schemaname='historian_raw' 
                  AND tablename='alarm_audit_trail'
                  AND indexname='idx_alarm_audit_occurrence'
            """)
            if not cur.fetchone():
                print("Creating idx_alarm_audit_occurrence...")
                cur.execute("""
                    CREATE INDEX idx_alarm_audit_occurrence 
                    ON historian_raw.alarm_audit_trail(occurrence_id)
                """)
                cur.execute("""
                    COMMENT ON INDEX historian_raw.idx_alarm_audit_occurrence IS 
                    'Performance index for filtering audit records by occurrence_id'
                """)
                print("✅ Created idx_alarm_audit_occurrence")
                changes_made.append("Created idx_alarm_audit_occurrence")
            else:
                print("⏭️  idx_alarm_audit_occurrence already exists")
        except Exception as e:
            print(f"❌ Error creating occurrence index: {e}")
            conn.rollback()
            return False
        
        # 6. Composite index for pagination
        try:
            cur.execute("""
                SELECT 1 FROM pg_indexes 
                WHERE schemaname='historian_raw' 
                  AND tablename='alarm_audit_trail'
                  AND indexname='idx_alarm_audit_event_sequence'
            """)
            if not cur.fetchone():
                print("Creating idx_alarm_audit_event_sequence...")
                cur.execute("""
                    CREATE INDEX idx_alarm_audit_event_sequence 
                    ON historian_raw.alarm_audit_trail(event_id, sequence_number)
                """)
                cur.execute("""
                    COMMENT ON INDEX historian_raw.idx_alarm_audit_event_sequence IS 
                    'Composite index for pagination queries using sequence_number'
                """)
                print("✅ Created idx_alarm_audit_event_sequence")
                changes_made.append("Created idx_alarm_audit_event_sequence")
            else:
                print("⏭️  idx_alarm_audit_event_sequence already exists")
        except Exception as e:
            print(f"❌ Error creating event_sequence index: {e}")
            conn.rollback()
            return False
        
        # Commit index creation
        conn.commit()
        print("\n✅ All indexes created successfully")
        
        # ===== VERIFY CHANGES =====
        print("\n🔍 Verifying Changes...")
        print("-" * 80)
        
        # Count columns
        cur.execute("""
            SELECT COUNT(*) FROM information_schema.columns 
            WHERE table_schema='historian_raw' 
              AND table_name='alarm_audit_trail'
        """)
        total_columns = cur.fetchone()[0]
        
        # Count indexes
        cur.execute("""
            SELECT COUNT(*) FROM pg_indexes 
            WHERE schemaname='historian_raw' 
              AND tablename='alarm_audit_trail'
        """)
        total_indexes = cur.fetchone()[0]
        
        print(f"✅ Total columns: {total_columns} (expected: 22)")
        print(f"✅ Total indexes: {total_indexes} (expected: 10)")
        
        # ===== SUMMARY =====
        print("\n" + "=" * 80)
        print("SUMMARY:")
        print("=" * 80)
        
        if changes_made:
            print(f"✅ Successfully applied {len(changes_made)} changes:")
            for i, change in enumerate(changes_made, 1):
                print(f"   {i}. {change}")
        else:
            print("✅ Schema already up-to-date - no changes needed")
        
        print("\n✅ Step 2.2 Complete - Database schema updated")
        
        cur.close()
        conn.close()
        
        return True
        
    except psycopg2.Error as e:
        print(f"\n❌ Database error: {e}")
        if 'conn' in locals():
            conn.rollback()
            conn.close()
        return False
    
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        if 'conn' in locals():
            conn.rollback()
            conn.close()
        return False

if __name__ == '__main__':
    success = add_columns_and_indexes()
    sys.exit(0 if success else 1)
