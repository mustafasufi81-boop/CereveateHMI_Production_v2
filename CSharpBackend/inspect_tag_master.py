import psycopg2
from psycopg2.extras import RealDictCursor
import json
import openpyxl

cfg = {
    'host': 'localhost',
    'port': 5432,
    'database': 'Automation_DB',
    'user': 'cereveate',
    'password': 'cereveate@222'
}

conn = psycopg2.connect(**cfg)
cur = conn.cursor(cursor_factory=RealDictCursor)

# 1. Show all columns
print('=' * 70)
print('  historian_meta.tag_master  -- COLUMN DEFINITIONS')
print('=' * 70)
cur.execute("""
    SELECT column_name, data_type, is_nullable, column_default, character_maximum_length
    FROM information_schema.columns
    WHERE table_schema='historian_meta' AND table_name='tag_master'
    ORDER BY ordinal_position
""")
cols_info = cur.fetchall()
for r in cols_info:
    print(f"  {r['column_name']:35s} | {r['data_type']:20s} | nullable={r['is_nullable']:3s} | default={str(r['column_default'])}")

# 2. Count
cur2 = conn.cursor()
cur2.execute("SELECT COUNT(*) FROM historian_meta.tag_master")
count = cur2.fetchone()[0]
print(f"\n  TOTAL EXISTING ROWS: {count}")

# 3. All existing rows
if count > 0:
    cur.execute("SELECT * FROM historian_meta.tag_master ORDER BY tag_id")
    rows = cur.fetchall()
    print(f"\n{'=' * 70}")
    print(f"  ALL {len(rows)} EXISTING ROWS (JSON)")
    print(f"{'=' * 70}")
    result = []
    for r in rows:
        d = dict(r)
        # convert non-serializable types
        for k, v in d.items():
            if v is not None and not isinstance(v, (str, int, float, bool)):
                d[k] = str(v)
        result.append(d)
        print(json.dumps(d))
    with open('tag_master_existing.json', 'w') as f:
        json.dump(result, f, indent=2)
    print(f"\n  >> Also saved to: tag_master_existing.json")
else:
    print("\n  Table is EMPTY.")

cur.close()
cur2.close()
conn.close()
print("\nDone.")
