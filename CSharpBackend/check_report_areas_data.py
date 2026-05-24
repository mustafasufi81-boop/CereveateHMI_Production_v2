import psycopg2
from psycopg2.extras import RealDictCursor

# Connect to database
conn = psycopg2.connect(
    host="localhost",
    port=5432,
    database="Automation_DB",
    user="cereveate",
    password="cereveate@222"
)

cur = conn.cursor(cursor_factory=RealDictCursor)

print("=" * 80)
print("CHECKING REPORT AREAS DATA")
print("=" * 80)

# Check areas endpoint query
query = """
    SELECT DISTINCT tm.plant, tm.area, tm.server_progid
    FROM historian_meta.tag_master tm
    WHERE tm.enabled = TRUE
      AND tm.include_in_report = TRUE
    ORDER BY tm.plant, tm.area, tm.server_progid
"""

print("\n1. QUERY USED BY /api/reports/areas:")
print(query)

cur.execute(query)
rows = cur.fetchall()

print(f"\n2. RESULT COUNT: {len(rows)} rows")

if rows:
    print("\n3. SAMPLE DATA (first 20 rows):")
    print("-" * 80)
    for i, row in enumerate(rows[:20]):
        print(f"{i+1}. Plant: {row['plant']}, Area: {row['area']}, Source: {row['server_progid']}")
else:
    print("\n⚠️ NO DATA RETURNED!")

# Check if include_in_report column exists
print("\n" + "=" * 80)
print("4. CHECKING include_in_report COLUMN:")
print("=" * 80)

cur.execute("""
    SELECT column_name, data_type, is_nullable, column_default
    FROM information_schema.columns
    WHERE table_schema = 'historian_meta' 
      AND table_name = 'tag_master' 
      AND column_name = 'include_in_report'
""")
col_info = cur.fetchone()

if col_info:
    print(f"✅ Column exists:")
    print(f"   Type: {col_info['data_type']}")
    print(f"   Nullable: {col_info['is_nullable']}")
    print(f"   Default: {col_info['column_default']}")
else:
    print("❌ Column 'include_in_report' NOT FOUND!")

# Check tag_master row counts
print("\n" + "=" * 80)
print("5. TAG_MASTER STATISTICS:")
print("=" * 80)

cur.execute("SELECT COUNT(*) as total FROM historian_meta.tag_master")
total = cur.fetchone()['total']
print(f"Total tags: {total}")

cur.execute("SELECT COUNT(*) as enabled FROM historian_meta.tag_master WHERE enabled = TRUE")
enabled = cur.fetchone()['enabled']
print(f"Enabled tags: {enabled}")

cur.execute("""
    SELECT COUNT(*) as included 
    FROM historian_meta.tag_master 
    WHERE enabled = TRUE AND include_in_report = TRUE
""")
included = cur.fetchone()['included']
print(f"Enabled + include_in_report = TRUE: {included}")

cur.execute("""
    SELECT COUNT(*) as with_source 
    FROM historian_meta.tag_master 
    WHERE enabled = TRUE 
      AND include_in_report = TRUE 
      AND server_progid IS NOT NULL 
      AND server_progid != ''
""")
with_source = cur.fetchone()['with_source']
print(f"With valid server_progid: {with_source}")

# Check unique sources
print("\n" + "=" * 80)
print("6. UNIQUE SOURCES IN DATABASE:")
print("=" * 80)

cur.execute("""
    SELECT DISTINCT server_progid, COUNT(*) as tag_count
    FROM historian_meta.tag_master
    WHERE enabled = TRUE AND include_in_report = TRUE
    GROUP BY server_progid
    ORDER BY server_progid
""")
sources = cur.fetchall()

if sources:
    for src in sources:
        print(f"   {src['server_progid']}: {src['tag_count']} tags")
else:
    print("   ⚠️ No sources found!")

# Check if server_progid is NULL or empty
print("\n" + "=" * 80)
print("7. CHECKING NULL/EMPTY server_progid:")
print("=" * 80)

cur.execute("""
    SELECT 
        COUNT(*) FILTER (WHERE server_progid IS NULL) as null_count,
        COUNT(*) FILTER (WHERE server_progid = '') as empty_count,
        COUNT(*) FILTER (WHERE server_progid IS NOT NULL AND server_progid != '') as valid_count
    FROM historian_meta.tag_master
    WHERE enabled = TRUE AND include_in_report = TRUE
""")
progid_stats = cur.fetchone()
print(f"NULL server_progid: {progid_stats['null_count']}")
print(f"Empty string server_progid: {progid_stats['empty_count']}")
print(f"Valid server_progid: {progid_stats['valid_count']}")

cur.close()
conn.close()

print("\n" + "=" * 80)
print("DIAGNOSIS COMPLETE")
print("=" * 80)
