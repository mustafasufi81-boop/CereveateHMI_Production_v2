import json
import psycopg2
import psycopg2.extras

DBS = [
    "Automation_DB",
    "Cereveate",
]

USER = "cereveate"
PASSWORD = "cereveate@222"
HOST = "localhost"
PORT = 5432

RELEVANT_TABLES = {
    "historian_raw": [
        "historian_timeseries",
        "historian_events",
        "historian_calc_values",
        "historian_latest_value",
        "alarm_active",
        "alarm_audit_trail",
        "trip_event_tracking",
        "mqtt_topic_config",
    ],
    "historian_meta": [
        "tag_master",
        "tag_attributes",
        "equipment_hierarchy",
    ],
    "historian_mon": [
        "system_metrics",
    ],
    "public": [
        "sensor_data",
        "file_imports",
        "tag_catalog",
        "import_errors",
        "latest_sensor_values",
        "import_summary_dashboard",
        "sensor_data_1min",
        "sensor_data_1hour",
    ],
}


def fetch_all(cur, query, params=None):
    cur.execute(query, params or ())
    return cur.fetchall()


def try_fetch_all(cur, query, params=None):
    try:
        cur.execute(query, params or ())
        return cur.fetchall(), None
    except Exception as exc:
        cur.connection.rollback()
        return [], exc


for db in DBS:
    conn = psycopg2.connect(host=HOST, port=PORT, dbname=db, user=USER, password=PASSWORD)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    print("=" * 100)
    print(f"DATABASE: {db}")
    print("=" * 100)

    schemas = fetch_all(cur, """
        SELECT schema_name
        FROM information_schema.schemata
        WHERE schema_name IN ('historian_raw', 'historian_meta', 'historian_mon', 'historian_admin', 'public')
        ORDER BY schema_name
    """)
    print("Schemas:", [r["schema_name"] for r in schemas])

    tables = fetch_all(cur, """
        SELECT table_schema, table_name, table_type
        FROM information_schema.tables
        WHERE table_schema IN ('historian_raw', 'historian_meta', 'historian_mon', 'historian_admin', 'public')
        ORDER BY table_schema, table_name
    """)

    relevant_found = []
    for schema, names in RELEVANT_TABLES.items():
        for name in names:
            match = next((t for t in tables if t["table_schema"] == schema and t["table_name"] == name), None)
            if match:
                relevant_found.append(f"{schema}.{name} [{match['table_type']}]")
    print("Relevant objects found:")
    for item in relevant_found:
        print(" -", item)

    extensions = fetch_all(cur, """
        SELECT extname
        FROM pg_extension
        WHERE extname = 'timescaledb'
    """)
    print("TimescaleDB installed:", bool(extensions))

    hypertables, hypertable_error = try_fetch_all(cur, """
        SELECT hypertable_schema, hypertable_name, num_chunks, compression_enabled
        FROM timescaledb_information.hypertables
        ORDER BY hypertable_schema, hypertable_name
    """)
    print("Hypertables:")
    if hypertable_error:
        print(f" - unavailable ({hypertable_error.__class__.__name__})")
    else:
        for h in hypertables:
            print(f" - {h['hypertable_schema']}.{h['hypertable_name']} chunks={h['num_chunks']} compressed={h['compression_enabled']}")

    caggs, cagg_error = try_fetch_all(cur, """
        SELECT view_schema, view_name
        FROM timescaledb_information.continuous_aggregates
        ORDER BY view_schema, view_name
    """)
    print("Continuous aggregates:")
    if cagg_error:
        print(f" - unavailable ({cagg_error.__class__.__name__})")
    else:
        for c in caggs:
            print(f" - {c['view_schema']}.{c['view_name']}")

    jobs, jobs_error = try_fetch_all(cur, """
        SELECT application_name, schedule_interval
        FROM timescaledb_information.jobs
        ORDER BY application_name
    """)
    print("Timescale jobs:")
    if jobs_error:
        print(f" - unavailable ({jobs_error.__class__.__name__})")
    else:
        for j in jobs:
            print(f" - {j['application_name']} @ {j['schedule_interval']}")

    print("Relevant row counts:")
    for schema, names in RELEVANT_TABLES.items():
        for name in names:
            exists = next((t for t in tables if t["table_schema"] == schema and t["table_name"] == name), None)
            if not exists or exists["table_type"] not in ("BASE TABLE", "VIEW", "MATERIALIZED VIEW"):
                continue
            try:
                cur.execute(f'SELECT COUNT(*) AS count FROM "{schema}"."{name}"')
                count = cur.fetchone()["count"]
                print(f" - {schema}.{name}: {count}")
            except Exception as exc:
                conn.rollback()
                print(f" - {schema}.{name}: count failed ({exc.__class__.__name__})")

    conn.close()
    print()
