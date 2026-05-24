import psycopg2
from pathlib import Path

sql_path = Path(__file__).with_name("dedupe_and_alter.sql")

conn = psycopg2.connect(
    host="localhost",
    port=5432,
    database="Cereveate",
    user="cereveate",
    password="cereveate@222",
)
conn.autocommit = False
cur = conn.cursor()

with sql_path.open("r", encoding="utf-8") as sql_file:
    sql = sql_file.read().replace("\r\n", "\n")

for statement in sql.split(";\n"):
    stmt = statement.strip()
    if not stmt or stmt.upper() == "BEGIN" or stmt.upper() == "COMMIT":
        continue
    print(f"Executing SQL: {stmt[:80]}...")
    cur.execute(stmt)

conn.commit()
cur.close()
conn.close()
