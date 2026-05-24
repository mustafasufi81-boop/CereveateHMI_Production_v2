import psycopg2

conn = psycopg2.connect(
    host='localhost',
    database='Cereveate',
    user='cereveate',
    password='cereveate@222'
)
cur = conn.cursor()

# Check if table exists
cur.execute("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'tag_file_catalog')")
exists = cur.fetchone()[0]
print(f'tag_file_catalog table exists: {exists}')

if not exists:
    print('\nCreating tag_file_catalog table...')
    with open('create_tag_file_catalog.sql', 'r') as f:
        sql = f.read()
    cur.execute(sql)
    conn.commit()
    print('Table created successfully!')
else:
    print('\nTable already exists. Checking structure...')
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'tag_file_catalog' ORDER BY ordinal_position")
    cols = [row[0] for row in cur.fetchall()]
    print('Columns:', ', '.join(cols))

cur.close()
conn.close()
