import psycopg2

conn = psycopg2.connect(
    host="localhost",
    port=5432,
    database="Cereveate",
    user="cereveate",
    password="cereveate@222"
)

cur = conn.cursor()

print("\n" + "="*80)
print("TABLE STRUCTURE CHECK - historian_raw.historian_timeseries")
print("="*80)

# Check if table exists
cur.execute("""
SELECT EXISTS (
    SELECT FROM information_schema.tables 
    WHERE table_schema = 'historian_raw' 
    AND table_name = 'historian_timeseries'
);
""")
exists = cur.fetchone()[0]

if not exists:
    print("❌ Table does NOT exist!")
else:
    print("✅ Table exists")
    
    # Check columns
    print("\n" + "="*80)
    print("COLUMN STRUCTURE")
    print("="*80)
    
    cur.execute("""
    SELECT 
        column_name, 
        data_type, 
        is_nullable,
        column_default
    FROM information_schema.columns 
    WHERE table_schema = 'historian_raw' 
    AND table_name = 'historian_timeseries'
    ORDER BY ordinal_position;
    """)
    
    columns = cur.fetchall()
    print(f"\nFound {len(columns)} columns:")
    for col in columns:
        nullable = "NULL" if col[2] == 'YES' else "NOT NULL"
        default = f", default={col[3]}" if col[3] else ""
        print(f"  {col[0]:<20} {col[1]:<25} {nullable}{default}")
    
    # Check constraints
    print("\n" + "="*80)
    print("CONSTRAINTS")
    print("="*80)
    
    cur.execute("""
    SELECT 
        conname as constraint_name,
        contype as constraint_type,
        pg_get_constraintdef(c.oid) as definition
    FROM pg_constraint c
    JOIN pg_namespace n ON n.oid = c.connamespace
    WHERE n.nspname = 'historian_raw'
    AND c.conrelid = 'historian_raw.historian_timeseries'::regclass;
    """)
    
    constraints = cur.fetchall()
    if constraints:
        for c in constraints:
            ctype = {'p': 'PRIMARY KEY', 'c': 'CHECK', 'f': 'FOREIGN KEY', 'u': 'UNIQUE'}.get(c[1], c[1])
            print(f"\n{c[0]} ({ctype}):")
            print(f"  {c[2]}")
    else:
        print("No constraints found")
    
    # Check indexes
    print("\n" + "="*80)
    print("INDEXES")
    print("="*80)
    
    cur.execute("""
    SELECT 
        indexname,
        indexdef
    FROM pg_indexes
    WHERE schemaname = 'historian_raw'
    AND tablename = 'historian_timeseries';
    """)
    
    indexes = cur.fetchall()
    if indexes:
        for idx in indexes:
            print(f"\n{idx[0]}:")
            print(f"  {idx[1]}")
    else:
        print("⚠️ No indexes found")
    
    # Check if table is hypertable (TimescaleDB)
    print("\n" + "="*80)
    print("TIMESCALEDB CHECK")
    print("="*80)
    
    try:
        cur.execute("""
        SELECT * FROM timescaledb_information.hypertables 
        WHERE hypertable_schema = 'historian_raw' 
        AND hypertable_name = 'historian_timeseries';
        """)
        hypertable = cur.fetchone()
        if hypertable:
            print("✅ Table is a TimescaleDB hypertable")
        else:
            print("⚠️ Table is NOT a hypertable")
    except:
        print("⚠️ TimescaleDB extension not found or not enabled")

# Check table ownership/permissions
print("\n" + "="*80)
print("PERMISSIONS")
print("="*80)

cur.execute("""
SELECT 
    grantee,
    privilege_type
FROM information_schema.role_table_grants
WHERE table_schema = 'historian_raw'
AND table_name = 'historian_timeseries'
AND grantee IN ('cereveate', 'PUBLIC');
""")

perms = cur.fetchall()
if perms:
    for p in perms:
        print(f"  {p[0]}: {p[1]}")
else:
    print("⚠️ No permissions found for cereveate user")

cur.close()
conn.close()

print("\n" + "="*80)
