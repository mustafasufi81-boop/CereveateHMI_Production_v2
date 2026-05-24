import psycopg2

try:
    conn = psycopg2.connect(
        host='localhost',
        port=5432,
        dbname='Cereveate',
        user='cereveate',
        password='cereveate@222'
    )

    cur = conn.cursor()

    # Test the exact query from app.py
    query = """
        SELECT tag_id, tag_name, description, plant, area, equipment, data_type, eng_unit
        FROM historian_meta.tag_master
        WHERE enabled = true
        ORDER BY tag_id
    """
    
    print("🔍 Testing query from app.py...")
    print(f"Query: {query}")
    print("-" * 80)
    
    cur.execute(query)
    rows = cur.fetchall()
    
    print(f"✅ Query succeeded! Found {len(rows)} rows\n")
    
    if rows:
        print("First 3 tags:")
        for i, row in enumerate(rows[:3]):
            print(f"\n  Row {i+1}:")
            print(f"    [0] tag_id: {row[0]}")
            print(f"    [1] tag_name: {row[1]}")
            print(f"    [2] description: {row[2]}")
            print(f"    [3] plant: {row[3]}")
            print(f"    [4] area: {row[4]}")
            print(f"    [5] equipment: {row[5]}")
            print(f"    [6] data_type: {row[6]}")
            print(f"    [7] eng_unit: {row[7]}")
    else:
        print("⚠️  No rows found!")
    
    # Now try building the JSON like the app does
    print("\n📦 Building JSON response like app.py...")
    tags = []
    for row in rows:
        tags.append({
            'tagId': row[0],
            'tagName': row[1],
            'description': row[2],
            'plant': row[3],
            'area': row[4],
            'equipment': row[5],
            'dataType': row[6],
            'unit': row[7]
        })
    
    print(f"✅ Successfully built {len(tags)} tag objects")
    if tags:
        print(f"\nSample tag object: {tags[0]}")
    
    cur.close()
    conn.close()
    
    print("\n✅ Test completed successfully!")

except Exception as e:
    print(f"\n❌ ERROR: {e}")
    print(f"   Error type: {type(e).__name__}")
    import traceback
    traceback.print_exc()
