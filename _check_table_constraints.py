"""
Check alarm_audit_trail table constraints, foreign keys, and dependencies
This helps understand why schema modifications might fail
"""

import psycopg2
import sys

# Database connection parameters
DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'Automation_DB',
    'user': 'cereveate',
    'password': 'cereveate@222'
}

def check_constraints():
    """Check all constraints on alarm_audit_trail table"""
    conn = None
    try:
        print("=" * 80)
        print("CHECKING alarm_audit_trail TABLE CONSTRAINTS")
        print("=" * 80)
        
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        
        # 1. Check PRIMARY KEY
        print("\n1. PRIMARY KEY CONSTRAINTS:")
        print("-" * 80)
        cur.execute("""
            SELECT 
                tc.constraint_name,
                kcu.column_name,
                tc.constraint_type
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu 
                ON tc.constraint_name = kcu.constraint_name
                AND tc.table_schema = kcu.table_schema
            WHERE tc.table_schema = 'historian_raw'
                AND tc.table_name = 'alarm_audit_trail'
                AND tc.constraint_type = 'PRIMARY KEY'
            ORDER BY kcu.ordinal_position;
        """)
        pk_results = cur.fetchall()
        if pk_results:
            for row in pk_results:
                print(f"  Constraint: {row[0]}")
                print(f"  Column: {row[1]}")
                print(f"  Type: {row[2]}")
        else:
            print("  ⚠️  NO PRIMARY KEY FOUND")
        
        # 2. Check FOREIGN KEY constraints
        print("\n2. FOREIGN KEY CONSTRAINTS:")
        print("-" * 80)
        cur.execute("""
            SELECT 
                tc.constraint_name,
                kcu.column_name,
                ccu.table_schema AS foreign_table_schema,
                ccu.table_name AS foreign_table_name,
                ccu.column_name AS foreign_column_name,
                rc.update_rule,
                rc.delete_rule
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu 
                ON tc.constraint_name = kcu.constraint_name
                AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage ccu
                ON ccu.constraint_name = tc.constraint_name
                AND ccu.table_schema = tc.table_schema
            JOIN information_schema.referential_constraints rc
                ON rc.constraint_name = tc.constraint_name
                AND rc.constraint_schema = tc.table_schema
            WHERE tc.table_schema = 'historian_raw'
                AND tc.table_name = 'alarm_audit_trail'
                AND tc.constraint_type = 'FOREIGN KEY'
            ORDER BY tc.constraint_name;
        """)
        fk_results = cur.fetchall()
        if fk_results:
            for row in fk_results:
                print(f"\n  FK Constraint: {row[0]}")
                print(f"  Local Column: {row[1]}")
                print(f"  References: {row[2]}.{row[3]}({row[4]})")
                print(f"  ON UPDATE: {row[5]}")
                print(f"  ON DELETE: {row[6]}")
        else:
            print("  ✓ No foreign key constraints")
        
        # 3. Check UNIQUE constraints
        print("\n3. UNIQUE CONSTRAINTS:")
        print("-" * 80)
        cur.execute("""
            SELECT 
                tc.constraint_name,
                kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu 
                ON tc.constraint_name = kcu.constraint_name
                AND tc.table_schema = kcu.table_schema
            WHERE tc.table_schema = 'historian_raw'
                AND tc.table_name = 'alarm_audit_trail'
                AND tc.constraint_type = 'UNIQUE'
            ORDER BY tc.constraint_name, kcu.ordinal_position;
        """)
        unique_results = cur.fetchall()
        if unique_results:
            for row in unique_results:
                print(f"  Constraint: {row[0]}")
                print(f"  Column: {row[1]}")
        else:
            print("  ✓ No unique constraints")
        
        # 4. Check CHECK constraints
        print("\n4. CHECK CONSTRAINTS:")
        print("-" * 80)
        cur.execute("""
            SELECT 
                tc.constraint_name,
                cc.check_clause
            FROM information_schema.table_constraints tc
            JOIN information_schema.check_constraints cc
                ON tc.constraint_name = cc.constraint_name
                AND tc.constraint_schema = cc.constraint_schema
            WHERE tc.table_schema = 'historian_raw'
                AND tc.table_name = 'alarm_audit_trail'
                AND tc.constraint_type = 'CHECK'
            ORDER BY tc.constraint_name;
        """)
        check_results = cur.fetchall()
        if check_results:
            for row in check_results:
                print(f"  Constraint: {row[0]}")
                print(f"  Check: {row[1]}")
        else:
            print("  ✓ No check constraints")
        
        # 5. Check NOT NULL constraints
        print("\n5. NOT NULL CONSTRAINTS:")
        print("-" * 80)
        cur.execute("""
            SELECT 
                column_name,
                data_type,
                is_nullable
            FROM information_schema.columns
            WHERE table_schema = 'historian_raw'
                AND table_name = 'alarm_audit_trail'
                AND is_nullable = 'NO'
            ORDER BY ordinal_position;
        """)
        notnull_results = cur.fetchall()
        if notnull_results:
            print(f"  Found {len(notnull_results)} NOT NULL columns:")
            for row in notnull_results:
                print(f"    - {row[0]} ({row[1]})")
        else:
            print("  ✓ No NOT NULL constraints")
        
        # 6. Check dependencies (views, functions that reference this table)
        print("\n6. TABLE DEPENDENCIES:")
        print("-" * 80)
        cur.execute("""
            SELECT DISTINCT
                dependent_ns.nspname as dependent_schema,
                dependent_view.relname as dependent_view,
                dependent_view.relkind as object_type
            FROM pg_depend 
            JOIN pg_rewrite ON pg_depend.objid = pg_rewrite.oid 
            JOIN pg_class as dependent_view ON pg_rewrite.ev_class = dependent_view.oid 
            JOIN pg_class as source_table ON pg_depend.refobjid = source_table.oid 
            JOIN pg_namespace dependent_ns ON dependent_ns.oid = dependent_view.relnamespace
            JOIN pg_namespace source_ns ON source_ns.oid = source_table.relnamespace
            WHERE source_ns.nspname = 'historian_raw'
                AND source_table.relname = 'alarm_audit_trail'
                AND dependent_view.relname != 'alarm_audit_trail'
            ORDER BY dependent_schema, dependent_view;
        """)
        dep_results = cur.fetchall()
        if dep_results:
            print(f"  ⚠️  Found {len(dep_results)} dependent objects:")
            for row in dep_results:
                obj_type = 'VIEW' if row[2] == 'v' else 'TABLE' if row[2] == 'r' else row[2]
                print(f"    - {row[0]}.{row[1]} ({obj_type})")
                print(f"      → May need to DROP CASCADE or recreate after schema changes")
        else:
            print("  ✓ No dependent views or functions")
        
        # 7. Check triggers
        print("\n7. TRIGGERS:")
        print("-" * 80)
        cur.execute("""
            SELECT 
                trigger_name,
                event_manipulation,
                action_timing,
                action_statement
            FROM information_schema.triggers
            WHERE event_object_schema = 'historian_raw'
                AND event_object_table = 'alarm_audit_trail'
            ORDER BY trigger_name;
        """)
        trigger_results = cur.fetchall()
        if trigger_results:
            print(f"  ⚠️  Found {len(trigger_results)} triggers:")
            for row in trigger_results:
                print(f"\n    Trigger: {row[0]}")
                print(f"    Event: {row[1]} {row[2]}")
                print(f"    Action: {row[3][:100]}...")
        else:
            print("  ✓ No triggers")
        
        # 8. Check table locks
        print("\n8. CURRENT TABLE LOCKS:")
        print("-" * 80)
        cur.execute("""
            SELECT 
                l.locktype,
                l.mode,
                l.granted,
                a.query,
                a.state,
                a.pid
            FROM pg_locks l
            JOIN pg_class c ON l.relation = c.oid
            JOIN pg_namespace n ON c.relnamespace = n.oid
            LEFT JOIN pg_stat_activity a ON l.pid = a.pid
            WHERE n.nspname = 'historian_raw'
                AND c.relname = 'alarm_audit_trail'
                AND l.pid != pg_backend_pid()
            ORDER BY l.granted DESC, l.mode;
        """)
        lock_results = cur.fetchall()
        if lock_results:
            print(f"  ⚠️  Found {len(lock_results)} active locks:")
            for row in lock_results:
                print(f"\n    Lock Type: {row[0]}")
                print(f"    Mode: {row[1]}")
                print(f"    Granted: {row[2]}")
                print(f"    PID: {row[5]}")
                print(f"    Query: {row[3][:80] if row[3] else 'N/A'}...")
        else:
            print("  ✓ No locks (table is free for modifications)")
        
        print("\n" + "=" * 80)
        print("CONSTRAINT CHECK COMPLETE")
        print("=" * 80)
        
        cur.close()
        
    except psycopg2.Error as e:
        print(f"\n❌ Database error: {e}")
        print(f"   Error code: {e.pgcode}")
        print(f"   Error details: {e.pgerror}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        sys.exit(1)
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    check_constraints()
