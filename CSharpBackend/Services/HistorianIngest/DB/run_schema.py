import psycopg2
import sys

DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'Cereveate',
    'user': 'cereveate',
    'password': 'cereveate@222'
}

def run_schema_migration():
    try:
        print(f"Connecting to database '{DB_CONFIG['database']}'...")
        conn = psycopg2.connect(**DB_CONFIG)
        conn.autocommit = False
        cur = conn.cursor()

        print("Connected successfully!")

        sql_file = 'Services/HistorianIngest/DB/production_schema.sql'
        print(f"Reading {sql_file}...")

        with open(sql_file, 'r', encoding='utf-8') as f:
            sql_content = f.read()

        print("Executing schema migration...")

        # Split SQL into individual statements safely
        statements = [s.strip() for s in sql_content.split(';') if s.strip()]

        for stmt in statements:
            try:
                cur.execute(stmt + ';')
            except psycopg2.Error as e:
                print("\n✗ SQL execution error:")
                print("------------------------------------------------")
                print(stmt)
                print("------------------------------------------------")
                print(f"Error: {e}")
                conn.rollback()
                return False

        conn.commit()
        print("✓ Schema migration completed successfully!")

        # Check tables created
        cur.execute("""
            SELECT schemaname, tablename 
            FROM pg_tables 
            WHERE schemaname IN ('historian_meta', 'historian_raw', 'historian_admin', 'historian_mon')
            ORDER BY schemaname, tablename;
        """)
        
        tables = cur.fetchall()

        print(f"\n✓ Verified {len(tables)} tables exist:")
        for schema, table in tables:
            print(f"  - {schema}.{table}")

        cur.close()
        conn.close()
        return True

    except psycopg2.Error as e:
        print(f"\n✗ Database error: {e}")
        print(f"  PG code: {e.pgcode}")
        return False
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        return False

if __name__ == '__main__':
    success = run_schema_migration()
    sys.exit(0 if success else 1)
