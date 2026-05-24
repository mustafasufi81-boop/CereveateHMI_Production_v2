"""
Check historian_meta.tag_master table and list ALL tags
"""
import psycopg2

# Database connection
conn = psycopg2.connect(
    host="localhost",
    port=5432,
    database="historian",
    user="postgres",
    password="postgres"
)

print("=" * 80)
print("CHECKING historian_meta.tag_master TABLE")
print("=" * 80)

cursor = conn.cursor()

# Check if table exists
cursor.execute("""
    SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'historian_meta' 
        AND table_name = 'tag_master'
    );
""")
exists = cursor.fetchone()[0]

if not exists:
    print("❌ Table historian_meta.tag_master does NOT exist!")
    cursor.close()
    conn.close()
    exit(1)

print("✅ Table historian_meta.tag_master exists\n")

# Count total tags
cursor.execute("SELECT COUNT(*) FROM historian_meta.tag_master")
total = cursor.fetchone()[0]
print(f"📊 Total tags in table: {total}")

# Count enabled tags
cursor.execute("SELECT COUNT(*) FROM historian_meta.tag_master WHERE enabled = true")
enabled = cursor.fetchone()[0]
print(f"✅ Enabled tags: {enabled}")
print(f"❌ Disabled tags: {total - enabled}\n")

# Show all tags
print("=" * 80)
print("ALL TAGS IN historian_meta.tag_master:")
print("=" * 80)

cursor.execute("""
    SELECT tag_id, tag_name, data_type, enabled, 
           plant, area, equipment, created_at
    FROM historian_meta.tag_master
    ORDER BY enabled DESC, tag_id
""")

rows = cursor.fetchall()

if not rows:
    print("⚠️  NO TAGS FOUND IN TABLE!")
    print("\nTo add tags, run:")
    print("INSERT INTO historian_meta.tag_master (tag_id, tag_name, data_type, enabled, created_by)")
    print("VALUES ('Random.Int1', 'Random Integer', 'Int32', true, 'HMI');")
else:
    for i, row in enumerate(rows, 1):
        tag_id, tag_name, data_type, enabled, plant, area, equipment, created_at = row
        status = "✅ ENABLED" if enabled else "❌ DISABLED"
        print(f"\n{i}. {status}")
        print(f"   Tag ID: {tag_id}")
        print(f"   Name: {tag_name}")
        print(f"   Type: {data_type}")
        if plant:
            print(f"   Plant: {plant}")
        if area:
            print(f"   Area: {area}")
        if equipment:
            print(f"   Equipment: {equipment}")
        print(f"   Created: {created_at}")

cursor.close()
conn.close()

print("\n" + "=" * 80)
print(f"✅ Found {total} tags ({enabled} enabled)")
print("=" * 80)
