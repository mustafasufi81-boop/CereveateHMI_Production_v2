"""Utility script to clear PostgresLogger ingestion tables for a clean restart."""

import psycopg2

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "database": "Cereveate",
    "user": "cereveate",
    "password": "cereveate@222",
}

TABLES = [
    "sensor_data",
    "tag_imports",
    "tag_file_catalog",
    "tag_catalog",
    "file_imports",
]


def main() -> None:
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            cur.execute("SET timescaledb.max_tuples_decompressed_per_dml_transaction TO 0")
            truncate_stmt = (
                "TRUNCATE TABLE "
                + ", ".join(TABLES)
                + " RESTART IDENTITY CASCADE"
            )
            cur.execute(truncate_stmt)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
