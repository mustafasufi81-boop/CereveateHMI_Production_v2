import psycopg2
import psycopg2.extras

conn = psycopg2.connect(
    host='localhost',
    port=5432,
    dbname='Automation_DB',
    user='cereveate',
    password='cereveate@222',
)
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

tables = [
    ('historian_raw', 'historian_timeseries'),
    ('historian_raw', 'historian_events'),
    ('historian_raw', 'historian_calc_values'),
    ('historian_mon', 'system_metrics'),
]

print('TIMESCALE EXTENSION:')
cur.execute("SELECT extname, extversion FROM pg_extension WHERE extname = 'timescaledb'")
print(cur.fetchall())
print()

for schema, table in tables:
    print('=' * 100)
    print(f'{schema}.{table}')
    print('=' * 100)

    cur.execute(
        """
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_schema = %s AND table_name = %s
        ORDER BY ordinal_position
        """,
        (schema, table),
    )
    print('COLUMNS:')
    for row in cur.fetchall():
        print(f" - {row['column_name']} :: {row['data_type']} nullable={row['is_nullable']}")

    cur.execute(
        """
        SELECT tc.constraint_name, tc.constraint_type, string_agg(kcu.column_name, ', ' ORDER BY kcu.ordinal_position) AS columns
        FROM information_schema.table_constraints tc
        LEFT JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
         AND tc.table_schema = kcu.table_schema
         AND tc.table_name = kcu.table_name
        WHERE tc.table_schema = %s AND tc.table_name = %s
        GROUP BY tc.constraint_name, tc.constraint_type
        ORDER BY tc.constraint_type, tc.constraint_name
        """,
        (schema, table),
    )
    print('CONSTRAINTS:')
    for row in cur.fetchall():
        print(f" - {row['constraint_type']}: {row['constraint_name']} ({row['columns']})")

    cur.execute(
        """
        SELECT indexname, indexdef
        FROM pg_indexes
        WHERE schemaname = %s AND tablename = %s
        ORDER BY indexname
        """,
        (schema, table),
    )
    print('INDEXES:')
    for row in cur.fetchall():
        print(f" - {row['indexname']}: {row['indexdef']}")

    cur.execute(f'SELECT COUNT(*) AS count FROM "{schema}"."{table}"')
    print('ROW COUNT:', cur.fetchone()['count'])
    print()

conn.close()
