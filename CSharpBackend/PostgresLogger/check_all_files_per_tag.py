import psycopg2

conn = psycopg2.connect(
    host='localhost',
    database='Cereveate',
    user='cereveate',
    password='cereveate@222'
)
cur = conn.cursor()

# Check Saw-toothed tags across ALL files
print("Saw-toothed Waves.Int1 - ALL FILES:")
cur.execute("""
    SELECT file_path, file_hash, record_count, first_seen, last_seen
    FROM tag_file_catalog 
    WHERE tag_id = 'Saw-toothed Waves.Int1'
    ORDER BY last_seen DESC
""")
for row in cur.fetchall():
    filename = row[0].split('\\')[-1]
    print(f"  {filename}: {row[2]} records, data from {row[3].strftime('%Y-%m-%d')} to {row[4].strftime('%Y-%m-%d')}")

print("\nSaw-toothed Waves.Int2 - ALL FILES:")
cur.execute("""
    SELECT file_path, record_count
    FROM tag_file_catalog 
    WHERE tag_id = 'Saw-toothed Waves.Int2'
    ORDER BY last_seen DESC
""")
for row in cur.fetchall():
    filename = row[0].split('\\')[-1]
    print(f"  {filename}: {row[1]} records")

# Use the view to see summary
print("\n\n=== TAG FILES SUMMARY (using view) ===")
cur.execute("""
    SELECT tag_id, file_count, total_records, files
    FROM tag_files_view
    WHERE tag_id LIKE 'Saw-toothed%'
    ORDER BY tag_id
""")
for row in cur.fetchall():
    print(f"\n{row[0]}:")
    print(f"  Files: {row[1]}")
    print(f"  Total records: {row[2]}")
    print(f"  File list: {row[3]}")

cur.close()
conn.close()
