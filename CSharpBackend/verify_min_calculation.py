import psycopg2
from psycopg2.extras import RealDictCursor

conn = psycopg2.connect(
    host="localhost",
    port=5432,
    database="Automation_DB",
    user="cereveate",
    password="cereveate@222"
)

cur = conn.cursor(cursor_factory=RealDictCursor)

# Check the specific tags from screenshot
test_tags = ['Random.Int2', 'Random.Int4', 'Random.Int8', 'Random.Money', 'Random.Real4']

print("=" * 100)
print("CHECKING MIN VALUE CALCULATION FOR SPECIFIC TAGS")
print("=" * 100)

for tag in test_tags:
    print(f"\n{'='*100}")
    print(f"TAG: {tag}")
    print(f"{'='*100}")
    
    # Get hourly aggregates
    cur.execute("""
        SELECT 
            tag_id,
            local_date,
            local_hour,
            avg_val,
            max_val,
            min_val
        FROM historian_raw.v_daily_hourly_agg
        WHERE tag_id = %s
          AND local_date = CURRENT_DATE
        ORDER BY local_hour
    """, (tag,))
    
    rows = cur.fetchall()
    
    if not rows:
        print("⚠️ NO DATA FOUND FOR THIS TAG")
        continue
    
    print(f"\nFound {len(rows)} hourly records")
    print("\nHourly breakdown:")
    print(f"{'Hour':<6} {'Avg':<12} {'Max':<12} {'Min':<12}")
    print("-" * 50)
    
    all_avg = []
    all_max = []
    all_min = []
    
    for row in rows:
        hour = row['local_hour']
        avg = float(row['avg_val']) if row['avg_val'] is not None else None
        max_val = float(row['max_val']) if row['max_val'] is not None else None
        min_val = float(row['min_val']) if row['min_val'] is not None else None
        
        print(f"{hour:<6} {str(avg):<12} {str(max_val):<12} {str(min_val):<12}")
        
        if avg is not None:
            all_avg.append(avg)
        if max_val is not None:
            all_max.append(max_val)
        if min_val is not None:
            all_min.append(min_val)
    
    # Calculate aggregates
    print("\n" + "="*50)
    print("CALCULATED AGGREGATES:")
    print("="*50)
    
    if all_avg:
        row_avg = round(sum(all_avg) / len(all_avg), 2)
        print(f"Average (sum/count): {row_avg}")
    else:
        print("Average: None")
    
    if all_max:
        row_max = round(max(all_max), 2)
        print(f"Maximum (max of all max): {row_max}")
    else:
        print("Maximum: None")
    
    if all_min:
        row_min = round(min(all_min), 2)
        print(f"Minimum (min of all min): {row_min}")
        print(f"\nAll min values: {all_min}")
        print(f"Python min() result: {min(all_min)}")
    else:
        print("Minimum: None")

cur.close()
conn.close()

print("\n" + "=" * 100)
print("ANALYSIS COMPLETE")
print("=" * 100)
