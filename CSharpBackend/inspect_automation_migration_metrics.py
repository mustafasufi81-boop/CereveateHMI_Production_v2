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

queries = {
    'timeseries_range': """
        SELECT COUNT(*) AS total_rows,
               MIN(time) AS min_time,
               MAX(time) AS max_time,
               COUNT(*) FILTER (WHERE time >= NOW() - INTERVAL '1 day') AS rows_last_1d,
               COUNT(*) FILTER (WHERE time >= NOW() - INTERVAL '1 hour') AS rows_last_1h,
               COUNT(*) FILTER (WHERE time >= NOW() - INTERVAL '5 minutes') AS rows_last_5m
        FROM historian_raw.historian_timeseries
    """,
    'relation_sizes': """
        SELECT
          pg_size_pretty(pg_relation_size('historian_raw.historian_timeseries')) AS table_size,
          pg_size_pretty(pg_indexes_size('historian_raw.historian_timeseries')) AS indexes_size,
          pg_size_pretty(pg_total_relation_size('historian_raw.historian_timeseries')) AS total_size
    """,
    'stat_user_tables': """
        SELECT n_live_tup, n_dead_tup, vacuum_count, autovacuum_count, analyze_count, autoanalyze_count
        FROM pg_stat_user_tables
        WHERE schemaname = 'historian_raw' AND relname = 'historian_timeseries'
    """,
    'database_size': """
        SELECT pg_size_pretty(pg_database_size(current_database())) AS db_size
    """,
    'replication': """
        SELECT application_name, client_addr, state, sync_state
        FROM pg_stat_replication
    """,
    'long_tx': """
        SELECT pid, usename, state, now() - xact_start AS xact_age, query
        FROM pg_stat_activity
        WHERE xact_start IS NOT NULL
          AND now() - xact_start > interval '5 minutes'
        ORDER BY xact_start
        LIMIT 10
    """,
}

for name, sql in queries.items():
    print('=' * 100)
    print(name.upper())
    print('=' * 100)
    cur.execute(sql)
    rows = cur.fetchall()
    for row in rows:
        print(dict(row))
    if not rows:
        print('[]')
    print()

conn.close()
