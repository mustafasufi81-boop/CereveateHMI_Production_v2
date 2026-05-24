import psycopg2, psycopg2.extras

conn = psycopg2.connect(host='localhost', dbname='Automation_DB', user='cereveate', password='cereveate@222', port=5432)
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

tags = ['Triangle Waves.Int4', 'Triangle Waves.Real18', 'Triangle Waves.UInt1',
        'Triangle Waves.Real14', 'Random.UInt8', 'Triangle Waves.UInt2',
        'Random.Int4', 'Random.Real18', 'Random.Real4', 'Random.Real8']

for tag in tags:
    cur.execute("""
        SELECT COUNT(*) total,
               COUNT(value_num) num_count,
               COUNT(value_text) text_count,
               MIN(time) earliest, MAX(time) latest,
               COUNT(CASE WHEN DATE(time) >= '2026-05-17' AND DATE(time) <= '2026-05-18' THEN 1 END) in_range
        FROM historian_raw.historian_timeseries
        WHERE tag_id = %s
    """, (tag,))
    r = dict(cur.fetchone())
    print(f"{tag}: total={r['total']}, num={r['num_count']}, text={r['text_count']}, in_range={r['in_range']}, {r['earliest']} → {r['latest']}")

conn.close()
