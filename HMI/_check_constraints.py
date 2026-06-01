#!/usr/bin/env python3
"""Check plants_areas table constraints."""

import psycopg2
import json

with open('config.json') as f:
    config = json.load(f)

db = config['database']
conn = psycopg2.connect(
    host=db['host'], port=db['port'], 
    database=db['database'], user=db['user'], password=db['password']
)

print("PLANTS_AREAS TABLE CONSTRAINTS:")
print("=" * 80)

with conn.cursor() as cur:
    cur.execute("""
        SELECT conname, pg_get_constraintdef(oid) 
        FROM pg_constraint 
        WHERE conrelid='historian_meta.plants_areas'::regclass
    """)
    for name, definition in cur.fetchall():
        print(f"{name}:")
        print(f"  {definition}\n")

print("\nTABLE STRUCTURE:")
print("=" * 80)
with conn.cursor() as cur:
    cur.execute("""
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_schema='historian_meta' AND table_name='plants_areas'
        ORDER BY ordinal_position
    """)
    for col, dtype, nullable in cur.fetchall():
        print(f"  {col:20s} {dtype:20s} NULL={nullable}")

conn.close()
