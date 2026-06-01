#!/usr/bin/env python3
"""Check all indexes on plants_areas."""

import psycopg2
import json

with open('config.json') as f:
    config = json.load(f)

db = config['database']
conn = psycopg2.connect(
    host=db['host'], port=db['port'], 
    database=db['database'], user=db['user'], password=db['password']
)

print("PLANTS_AREAS INDEXES:")
print("=" * 80)

with conn.cursor() as cur:
    cur.execute("""
        SELECT indexname, indexdef 
        FROM pg_indexes 
        WHERE tablename='plants_areas' AND schemaname='historian_meta'
    """)
    for name, definition in cur.fetchall():
        print(f"{name}:")
        print(f"  {definition}\n")

conn.close()
